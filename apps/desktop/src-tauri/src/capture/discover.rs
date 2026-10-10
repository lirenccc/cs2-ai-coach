//! CS2 window discovery — process ownership first, title only as metadata.

use crate::capture::error::CaptureError;
use crate::capture::types::{CaptureTarget, CaptureTargetKind, RectPx};
use serde::{Deserialize, Serialize};

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct WindowCandidate {
    pub hwnd: u64,
    pub process_id: u32,
    pub title: String,
    pub class_name: String,
    pub client_width: u32,
    pub client_height: u32,
    pub frame_rect: RectPx,
    pub client_rect: RectPx,
    pub dpi_scale: f64,
    pub is_visible: bool,
    pub is_minimized: bool,
    pub is_tool_window: bool,
}

#[derive(Debug, Clone, PartialEq)]
pub enum DiscoveryOutcome {
    Found(CaptureTarget),
    NotFound,
    Ambiguous(Vec<CaptureTarget>),
    Minimized(CaptureTarget),
    ZeroSize(CaptureTarget),
}

/// Pure selection over already-enumerated candidates owned by `cs2_pid`.
pub fn select_cs2_main_window(
    cs2_pid: u32,
    candidates: &[WindowCandidate],
) -> Result<DiscoveryOutcome, CaptureError> {
    let owned: Vec<&WindowCandidate> = candidates
        .iter()
        .filter(|c| c.process_id == cs2_pid)
        .filter(|c| c.hwnd != 0)
        .collect();

    if owned.is_empty() {
        return Ok(DiscoveryOutcome::NotFound);
    }

    let capturable: Vec<&WindowCandidate> = owned
        .iter()
        .copied()
        .filter(|c| !c.is_tool_window)
        .filter(|c| c.is_visible || c.is_minimized)
        .collect();

    let pool = if capturable.is_empty() {
        owned
    } else {
        capturable
    };

    // Prefer largest non-zero client area among visible non-tool windows.
    let mut scored: Vec<&WindowCandidate> = pool;
    scored.sort_by_key(|c| {
        let area = (c.client_width as u64).saturating_mul(c.client_height as u64);
        (
            c.is_tool_window,
            !c.is_visible && !c.is_minimized,
            std::cmp::Reverse(area),
            c.hwnd,
        )
    });

    let best = scored[0];
    let best_area = (best.client_width as u64).saturating_mul(best.client_height as u64);

    // Ambiguous if another non-tool window has comparable area (≥80%).
    let rivals: Vec<&WindowCandidate> = scored
        .iter()
        .copied()
        .skip(1)
        .filter(|c| !c.is_tool_window)
        .filter(|c| {
            let area = (c.client_width as u64).saturating_mul(c.client_height as u64);
            best_area > 0 && area * 100 >= best_area * 80
        })
        .collect();

    if !rivals.is_empty() && best_area > 0 && !best.is_minimized {
        let mut targets: Vec<CaptureTarget> = std::iter::once(best)
            .chain(rivals)
            .map(candidate_to_target)
            .collect();
        targets.sort_by(|a, b| a.target_id.cmp(&b.target_id));
        return Ok(DiscoveryOutcome::Ambiguous(targets));
    }

    let target = candidate_to_target(best);
    if best.is_minimized {
        return Ok(DiscoveryOutcome::Minimized(target));
    }
    if best.client_width == 0 || best.client_height == 0 {
        return Ok(DiscoveryOutcome::ZeroSize(target));
    }
    if !best.is_visible {
        return Ok(DiscoveryOutcome::NotFound);
    }
    Ok(DiscoveryOutcome::Found(target))
}

pub fn outcome_to_result(outcome: DiscoveryOutcome) -> Result<CaptureTarget, CaptureError> {
    match outcome {
        DiscoveryOutcome::Found(t) => Ok(t),
        DiscoveryOutcome::NotFound => Err(CaptureError::window_not_found()),
        DiscoveryOutcome::Ambiguous(list) => Err(CaptureError::target_ambiguous(format!(
            "{} candidate main windows",
            list.len()
        ))),
        DiscoveryOutcome::Minimized(_) => Err(CaptureError::target_minimized()),
        DiscoveryOutcome::ZeroSize(_) => Err(CaptureError::target_zero_size()),
    }
}

fn candidate_to_target(c: &WindowCandidate) -> CaptureTarget {
    CaptureTarget {
        target_id: format!("hwnd-{}", c.hwnd),
        kind: CaptureTargetKind::Window,
        hwnd: Some(c.hwnd),
        process_id: Some(c.process_id),
        process_name: Some("cs2.exe".into()),
        title: Some(c.title.clone()),
        class_name: Some(c.class_name.clone()),
        client_rect: c.client_rect,
        frame_rect: c.frame_rect,
        dpi_scale: c.dpi_scale,
        monitor_id: None,
        is_minimized: c.is_minimized,
        is_visible: c.is_visible,
    }
}

/// Enumerate top-level windows owned by `cs2_pid` (Windows).
pub fn enumerate_cs2_windows(cs2_pid: u32) -> Result<Vec<WindowCandidate>, CaptureError> {
    #[cfg(windows)]
    {
        windows_enumerate(cs2_pid)
    }
    #[cfg(not(windows))]
    {
        let _ = cs2_pid;
        Err(CaptureError::unsupported(
            "CS2 window enumeration requires Windows",
        ))
    }
}

pub fn discover_cs2_target(cs2_pid: u32) -> Result<CaptureTarget, CaptureError> {
    let candidates = enumerate_cs2_windows(cs2_pid)?;
    outcome_to_result(select_cs2_main_window(cs2_pid, &candidates)?)
}

#[cfg(windows)]
fn windows_enumerate(cs2_pid: u32) -> Result<Vec<WindowCandidate>, CaptureError> {
    use windows::core::BOOL;
    use windows::Win32::Foundation::{HWND, LPARAM, RECT};
    use windows::Win32::UI::WindowsAndMessaging::{
        EnumWindows, GetClientRect, GetWindowLongW, GetWindowRect, GetWindowTextW,
        GetWindowThreadProcessId, IsIconic, IsWindow, IsWindowVisible, GWL_EXSTYLE,
        WINDOW_EX_STYLE, WS_EX_TOOLWINDOW,
    };

    struct State {
        pid: u32,
        out: Vec<WindowCandidate>,
    }

    unsafe extern "system" fn callback(hwnd: HWND, lparam: LPARAM) -> BOOL {
        let state = &mut *(lparam.0 as *mut State);
        if !IsWindow(Some(hwnd)).as_bool() {
            return BOOL(1);
        }
        let mut pid = 0u32;
        GetWindowThreadProcessId(hwnd, Some(&mut pid));
        if pid != state.pid {
            return BOOL(1);
        }

        let mut title_buf = [0u16; 512];
        let title_len = GetWindowTextW(hwnd, &mut title_buf);
        let title = String::from_utf16_lossy(&title_buf[..title_len as usize]);

        let mut class_buf = [0u16; 256];
        let class_len =
            windows::Win32::UI::WindowsAndMessaging::GetClassNameW(hwnd, &mut class_buf);
        let class_name = String::from_utf16_lossy(&class_buf[..class_len as usize]);

        let mut frame = RECT::default();
        let mut client = RECT::default();
        let _ = GetWindowRect(hwnd, &mut frame);
        let _ = GetClientRect(hwnd, &mut client);

        let ex = WINDOW_EX_STYLE(GetWindowLongW(hwnd, GWL_EXSTYLE) as u32);
        let is_tool_window = ex.contains(WS_EX_TOOLWINDOW);

        let dpi = windows::Win32::UI::HiDpi::GetDpiForWindow(hwnd);
        let dpi_scale = if dpi > 0 { dpi as f64 / 96.0 } else { 1.0 };

        let client_width = (client.right - client.left).max(0) as u32;
        let client_height = (client.bottom - client.top).max(0) as u32;

        state.out.push(WindowCandidate {
            hwnd: hwnd.0 as u64,
            process_id: pid,
            title,
            class_name,
            client_width,
            client_height,
            frame_rect: RectPx {
                x: frame.left,
                y: frame.top,
                width: (frame.right - frame.left).max(0) as u32,
                height: (frame.bottom - frame.top).max(0) as u32,
            },
            client_rect: RectPx {
                x: client.left,
                y: client.top,
                width: client_width,
                height: client_height,
            },
            dpi_scale,
            is_visible: IsWindowVisible(hwnd).as_bool(),
            is_minimized: IsIconic(hwnd).as_bool(),
            is_tool_window,
        });
        BOOL(1)
    }

    let mut state = State {
        pid: cs2_pid,
        out: Vec::new(),
    };
    unsafe {
        EnumWindows(Some(callback), LPARAM(&mut state as *mut State as isize)).map_err(|e| {
            CaptureError::new(
                "CAPTURE_CS2_WINDOW_NOT_FOUND",
                e.to_string(),
                Some("Ensure CS2 is running in offline Demo replay and the game window is open"),
            )
        })?;
    }
    Ok(state.out)
}

#[cfg(test)]
mod tests {
    use super::*;

    fn cand(
        hwnd: u64,
        pid: u32,
        w: u32,
        h: u32,
        visible: bool,
        minimized: bool,
        tool: bool,
    ) -> WindowCandidate {
        WindowCandidate {
            hwnd,
            process_id: pid,
            title: format!("win-{hwnd}"),
            class_name: "SDL_app".into(),
            client_width: w,
            client_height: h,
            frame_rect: RectPx {
                x: 0,
                y: 0,
                width: w,
                height: h,
            },
            client_rect: RectPx {
                x: 0,
                y: 0,
                width: w,
                height: h,
            },
            dpi_scale: 1.0,
            is_visible: visible,
            is_minimized: minimized,
            is_tool_window: tool,
        }
    }

    #[test]
    fn selects_largest_owned_window() {
        let list = vec![
            cand(1, 10, 800, 600, true, false, false),
            cand(2, 10, 1920, 1080, true, false, false),
            cand(3, 10, 200, 200, true, false, true),
            cand(4, 99, 2560, 1440, true, false, false),
        ];
        match select_cs2_main_window(10, &list).unwrap() {
            DiscoveryOutcome::Found(t) => assert_eq!(t.hwnd, Some(2)),
            other => panic!("unexpected {other:?}"),
        }
    }

    #[test]
    fn no_matching_window() {
        let list = vec![cand(1, 99, 800, 600, true, false, false)];
        assert!(matches!(
            select_cs2_main_window(10, &list).unwrap(),
            DiscoveryOutcome::NotFound
        ));
    }

    #[test]
    fn ambiguous_windows() {
        let list = vec![
            cand(1, 10, 1920, 1080, true, false, false),
            cand(2, 10, 1900, 1060, true, false, false),
        ];
        match select_cs2_main_window(10, &list).unwrap() {
            DiscoveryOutcome::Ambiguous(v) => assert_eq!(v.len(), 2),
            other => panic!("unexpected {other:?}"),
        }
    }

    #[test]
    fn zero_size_and_minimized() {
        let zero = vec![cand(1, 10, 0, 0, true, false, false)];
        assert!(matches!(
            select_cs2_main_window(10, &zero).unwrap(),
            DiscoveryOutcome::ZeroSize(_)
        ));
        let mini = vec![cand(1, 10, 1920, 1080, false, true, false)];
        assert!(matches!(
            select_cs2_main_window(10, &mini).unwrap(),
            DiscoveryOutcome::Minimized(_)
        ));
    }
}
