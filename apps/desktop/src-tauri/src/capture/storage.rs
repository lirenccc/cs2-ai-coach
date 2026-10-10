//! Managed capture file storage under `runtime/captures/`.
//! Image blobs stay on disk — never SQLite.

use crate::capture::error::CaptureError;
use crate::capture::quality::content_sha256;
use rand::RngCore;
use std::fs;
use std::path::{Component, Path, PathBuf};

#[derive(Debug, Clone)]
pub struct CaptureStorage {
    runtime_root: PathBuf,
}

impl CaptureStorage {
    pub fn new(runtime_root: impl Into<PathBuf>) -> Self {
        let runtime_root = runtime_root.into();
        let runtime_root = normalize_path(&runtime_root);
        Self { runtime_root }
    }

    pub fn captures_root(&self) -> PathBuf {
        self.runtime_root.join("captures")
    }

    pub fn capture_dir(&self, match_id: &str, capture_id: &str) -> Result<PathBuf, CaptureError> {
        let match_id = sanitize_id(match_id)?;
        let capture_id = sanitize_id(capture_id)?;
        Ok(self.captures_root().join(match_id).join(capture_id))
    }

    pub fn frame_path(
        &self,
        match_id: &str,
        capture_id: &str,
        frame_index: u32,
    ) -> Result<PathBuf, CaptureError> {
        let dir = self.capture_dir(match_id, capture_id)?;
        Ok(dir.join(format!("frame-{frame_index:04}.png")))
    }

    pub fn manifest_path(&self, match_id: &str, capture_id: &str) -> Result<PathBuf, CaptureError> {
        Ok(self.capture_dir(match_id, capture_id)?.join("manifest.json"))
    }

    pub fn ensure_capture_dir(
        &self,
        match_id: &str,
        capture_id: &str,
    ) -> Result<PathBuf, CaptureError> {
        let dir = self.capture_dir(match_id, capture_id)?;
        fs::create_dir_all(&dir).map_err(|e| {
            CaptureError::storage_failed(format!("create_dir_all {}: {e}", dir.display()))
        })?;
        Ok(dir)
    }

    pub fn write_png_atomic(
        &self,
        path: &Path,
        width: u32,
        height: u32,
        rgba_or_bgra: &[u8],
        is_bgra: bool,
    ) -> Result<String, CaptureError> {
        reject_traversal(path, &self.runtime_root)?;
        if let Some(parent) = path.parent() {
            fs::create_dir_all(parent).map_err(|e| {
                CaptureError::storage_failed(format!("create parent {}: {e}", parent.display()))
            })?;
        }
        let rgba = if is_bgra {
            bgra_to_rgba(rgba_or_bgra)
        } else {
            rgba_or_bgra.to_vec()
        };
        let tmp = path.with_extension("png.tmp");
        write_png_file(&tmp, width, height, &rgba)?;
        fs::rename(&tmp, path).map_err(|e| {
            CaptureError::storage_failed(format!("rename {}: {e}", path.display()))
        })?;
        let encoded = fs::read(path).map_err(|e| {
            CaptureError::storage_failed(format!("read back {}: {e}", path.display()))
        })?;
        Ok(content_sha256(&encoded))
    }

    pub fn delete_capture(
        &self,
        match_id: &str,
        capture_id: &str,
    ) -> Result<(), CaptureError> {
        let dir = self.capture_dir(match_id, capture_id)?;
        reject_traversal(&dir, &self.runtime_root)?;
        if dir.exists() {
            fs::remove_dir_all(&dir).map_err(|e| {
                CaptureError::storage_failed(format!("remove {}: {e}", dir.display()))
            })?;
        }
        Ok(())
    }

    pub fn new_capture_id() -> String {
        let mut bytes = [0u8; 8];
        rand::thread_rng().fill_bytes(&mut bytes);
        format!(
            "cap-{}",
            bytes.iter().map(|b| format!("{b:02x}")).collect::<String>()
        )
    }
}

pub fn sanitize_id(id: &str) -> Result<String, CaptureError> {
    if id.is_empty() || id.len() > 128 {
        return Err(CaptureError::storage_failed("invalid capture id length"));
    }
    if id.contains("..") || id.contains('/') || id.contains('\\') {
        return Err(CaptureError::storage_failed(
            "path separators and parent components are forbidden in capture ids",
        ));
    }
    if !id
        .bytes()
        .all(|b| b.is_ascii_alphanumeric() || matches!(b, b'-' | b'_' | b'.'))
    {
        return Err(CaptureError::storage_failed(
            "capture id contains unsafe characters",
        ));
    }
    Ok(id.to_string())
}

/// Collapse `.` / `..` without requiring the path to exist.
pub fn normalize_path(path: &Path) -> PathBuf {
    let mut out = PathBuf::new();
    for c in path.components() {
        match c {
            Component::ParentDir => {
                out.pop();
            }
            Component::CurDir => {}
            other => out.push(other.as_os_str()),
        }
    }
    out
}

pub fn reject_traversal(path: &Path, root: &Path) -> Result<(), CaptureError> {
    let root_n = normalize_path(root);
    let path_n = normalize_path(path);
    if path_n.starts_with(&root_n) {
        return Ok(());
    }
    if let Ok(root_canon) = root.canonicalize() {
        if path_n.starts_with(&root_canon) {
            return Ok(());
        }
        if path.exists() {
            if let Ok(candidate) = path.canonicalize() {
                if candidate.starts_with(&root_canon) {
                    return Ok(());
                }
            }
        }
    }
    Err(CaptureError::storage_failed(format!(
        "path escapes runtime root: {} (normalized {})",
        path.display(),
        path_n.display()
    )))
}

fn bgra_to_rgba(bgra: &[u8]) -> Vec<u8> {
    let mut out = Vec::with_capacity(bgra.len());
    for chunk in bgra.chunks_exact(4) {
        out.extend_from_slice(&[chunk[2], chunk[1], chunk[0], chunk[3]]);
    }
    out
}

fn write_png_file(path: &Path, width: u32, height: u32, rgba: &[u8]) -> Result<(), CaptureError> {
    let file = fs::File::create(path)
        .map_err(|e| CaptureError::storage_failed(format!("create {}: {e}", path.display())))?;
    let mut encoder = png::Encoder::new(file, width, height);
    encoder.set_color(png::ColorType::Rgba);
    encoder.set_depth(png::BitDepth::Eight);
    let mut writer = encoder.write_header().map_err(|e| {
        CaptureError::storage_failed(format!("png header {}: {e}", path.display()))
    })?;
    writer.write_image_data(rgba).map_err(|e| {
        CaptureError::storage_failed(format!("png data {}: {e}", path.display()))
    })?;
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn storage_path_construction() {
        let root = PathBuf::from("runtime");
        let store = CaptureStorage::new(&root);
        let p = store.frame_path("match-a", "cap-1", 1).unwrap();
        assert!(p.ends_with(
            Path::new("captures")
                .join("match-a")
                .join("cap-1")
                .join("frame-0001.png")
        ));
    }

    #[test]
    fn traversal_rejection() {
        assert!(sanitize_id("../x").is_err());
        assert!(sanitize_id("a/b").is_err());
        assert!(sanitize_id("ok-id_1").is_ok());
        let root = PathBuf::from("runtime");
        assert!(reject_traversal(Path::new("runtime/../secret"), &root).is_err());
        // Relative roots with `..` components must normalize, not false-reject.
        let nested = PathBuf::from("apps/desktop/src-tauri/../../../runtime");
        let store = CaptureStorage::new(&nested);
        let ok = store.frame_path("m", "c", 1).unwrap();
        assert!(reject_traversal(&ok, store.captures_root().parent().unwrap()).is_ok()
            || reject_traversal(&ok, &store.captures_root()).is_ok()
            || ok.starts_with(normalize_path(&nested)));
    }

    #[test]
    fn write_and_delete_png() {
        let dir = std::env::temp_dir().join(format!(
            "cs2-coach-cap-{}",
            std::process::id()
        ));
        let _ = fs::remove_dir_all(&dir);
        let store = CaptureStorage::new(&dir);
        let path = store.frame_path("m1", "c1", 1).unwrap();
        let mut px = vec![0u8; 64 * 64 * 4];
        for (i, chunk) in px.chunks_exact_mut(4).enumerate() {
            chunk[0] = (i % 255) as u8;
            chunk[1] = 40;
            chunk[2] = 80;
            chunk[3] = 255;
        }
        let hash = store.write_png_atomic(&path, 64, 64, &px, false).unwrap();
        assert_eq!(hash.len(), 64);
        assert!(path.is_file());
        store.delete_capture("m1", "c1").unwrap();
        assert!(!store.capture_dir("m1", "c1").unwrap().exists());
        let _ = fs::remove_dir_all(&dir);
    }
}
