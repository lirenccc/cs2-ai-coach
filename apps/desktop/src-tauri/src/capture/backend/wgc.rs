//! Windows.Graphics.Capture primary backend.
//!
//! HWND → IGraphicsCaptureItemInterop::CreateForWindow → GraphicsCaptureItem
//! → Direct3D11CaptureFramePool::CreateFreeThreaded → GraphicsCaptureSession
//! → Direct3D11CaptureFrame → CPU staging copy (BGRA8).
//!
//! COM/WinRT/D3D objects never escape this module.

#![cfg(windows)]

use crate::capture::error::CaptureError;
use crate::capture::types::{CaptureBackend, PixelFormat, ResizeRecoveryInfo};
use std::time::{Duration, Instant};
use windows::core::Interface;
use windows::Graphics::Capture::{
    Direct3D11CaptureFrame, Direct3D11CaptureFramePool, GraphicsCaptureItem, GraphicsCaptureSession,
};
use windows::Graphics::DirectX::Direct3D11::IDirect3DDevice;
use windows::Graphics::DirectX::DirectXPixelFormat;
use windows::Graphics::SizeInt32;
use windows::Win32::Foundation::{HMODULE, HWND};
use windows::Win32::Graphics::Direct3D::D3D_DRIVER_TYPE_HARDWARE;
use windows::Win32::Graphics::Direct3D11::{
    D3D11CreateDevice, ID3D11Device, ID3D11DeviceContext, ID3D11Texture2D, D3D11_CPU_ACCESS_READ,
    D3D11_CREATE_DEVICE_BGRA_SUPPORT, D3D11_MAPPED_SUBRESOURCE, D3D11_MAP_READ, D3D11_SDK_VERSION,
    D3D11_TEXTURE2D_DESC, D3D11_USAGE_STAGING,
};
use windows::Win32::Graphics::Dxgi::IDXGIDevice;
use windows::Win32::System::Com::{CoInitializeEx, COINIT_MULTITHREADED};
use windows::Win32::System::WinRT::Direct3D11::{
    CreateDirect3D11DeviceFromDXGIDevice, IDirect3DDxgiInterfaceAccess,
};
use windows::Win32::System::WinRT::Graphics::Capture::IGraphicsCaptureItemInterop;
use windows::Win32::UI::WindowsAndMessaging::IsWindow;

struct PoolGuard(Direct3D11CaptureFramePool);
impl Drop for PoolGuard {
    fn drop(&mut self) {
        let _ = self.0.Close();
    }
}
impl std::ops::Deref for PoolGuard {
    type Target = Direct3D11CaptureFramePool;
    fn deref(&self) -> &Self::Target {
        &self.0
    }
}

struct SessionGuard(GraphicsCaptureSession);
impl Drop for SessionGuard {
    fn drop(&mut self) {
        let _ = self.0.Close();
    }
}
impl std::ops::Deref for SessionGuard {
    type Target = GraphicsCaptureSession;
    fn deref(&self) -> &Self::Target {
        &self.0
    }
}

struct FrameGuard(Direct3D11CaptureFrame);
impl Drop for FrameGuard {
    fn drop(&mut self) {
        let _ = self.0.Close();
    }
}
impl std::ops::Deref for FrameGuard {
    type Target = Direct3D11CaptureFrame;
    fn deref(&self) -> &Self::Target {
        &self.0
    }
}

struct WgcDevice {
    device: ID3D11Device,
    context: ID3D11DeviceContext,
    rt_device: IDirect3DDevice,
}

fn ensure_com() {
    unsafe {
        let _ = CoInitializeEx(None, COINIT_MULTITHREADED);
    }
}

pub fn wgc_is_supported() -> bool {
    ensure_com();
    GraphicsCaptureSession::IsSupported().unwrap_or(false)
}

fn build_device() -> Result<WgcDevice, CaptureError> {
    ensure_com();
    unsafe {
        let mut device_opt: Option<ID3D11Device> = None;
        D3D11CreateDevice(
            None,
            D3D_DRIVER_TYPE_HARDWARE,
            HMODULE::default(),
            D3D11_CREATE_DEVICE_BGRA_SUPPORT,
            None,
            D3D11_SDK_VERSION,
            Some(&mut device_opt),
            None,
            None,
        )
        .map_err(|e| CaptureError::device_lost(format!("D3D11CreateDevice: {e}")))?;
        let device = device_opt.ok_or_else(|| CaptureError::device_lost("D3D11 device null"))?;
        let context = device
            .GetImmediateContext()
            .map_err(|e| CaptureError::device_lost(e.to_string()))?;
        let dxgi_device: IDXGIDevice = device
            .cast()
            .map_err(|e| CaptureError::device_lost(e.to_string()))?;
        let inspectable = CreateDirect3D11DeviceFromDXGIDevice(&dxgi_device)
            .map_err(|e| CaptureError::device_lost(e.to_string()))?;
        let rt_device: IDirect3DDevice = inspectable
            .cast()
            .map_err(|e| CaptureError::device_lost(e.to_string()))?;
        Ok(WgcDevice {
            device,
            context,
            rt_device,
        })
    }
}

#[derive(Debug, Clone)]
pub struct WgcRawFrame {
    pub width: u32,
    pub height: u32,
    pub pixels_bgra: Vec<u8>,
    pub pixel_format: PixelFormat,
    pub source_timestamp_qpc: Option<u64>,
    pub content_size_changed: bool,
    pub frame_pool_recreated: bool,
    pub old_size: Option<(u32, u32)>,
    pub new_size: Option<(u32, u32)>,
}

pub struct WgcCaptureSession {
    hwnd: HWND,
    device: WgcDevice,
    item: GraphicsCaptureItem,
    pool: PoolGuard,
    session: SessionGuard,
    last_content_size: SizeInt32,
    frame_pool_recreated: bool,
    last_resize: Option<ResizeRecoveryInfo>,
}

impl WgcCaptureSession {
    pub fn open(hwnd_raw: u64) -> Result<Self, CaptureError> {
        if !wgc_is_supported() {
            return Err(CaptureError::wgc_unavailable(
                "GraphicsCaptureSession::IsSupported returned false",
            ));
        }
        let hwnd = HWND(hwnd_raw as *mut core::ffi::c_void);
        if unsafe { !IsWindow(Some(hwnd)).as_bool() } {
            return Err(CaptureError::target_closed());
        }
        let device = build_device()?;
        let interop = windows::core::factory::<GraphicsCaptureItem, IGraphicsCaptureItemInterop>()
            .map_err(|e| CaptureError::wgc_unavailable(format!("interop factory: {e}")))?;
        let item: GraphicsCaptureItem = unsafe { interop.CreateForWindow(hwnd) }
            .map_err(|e| CaptureError::target_closed_detail(format!("CreateForWindow: {e}")))?;
        let size = item
            .Size()
            .map_err(|e| CaptureError::copy_failed(e.to_string()))?;
        if size.Width <= 0 || size.Height <= 0 {
            return Err(CaptureError::target_zero_size());
        }
        let pool = PoolGuard(
            Direct3D11CaptureFramePool::CreateFreeThreaded(
                &device.rt_device,
                DirectXPixelFormat::B8G8R8A8UIntNormalized,
                2,
                size,
            )
            .map_err(|e| CaptureError::device_lost(format!("CreateFreeThreaded: {e}")))?,
        );
        let session = SessionGuard(
            pool.CreateCaptureSession(&item)
                .map_err(|e| CaptureError::device_lost(format!("CreateCaptureSession: {e}")))?,
        );
        let _ = session.SetIsCursorCaptureEnabled(false);
        let _ = session.SetIsBorderRequired(false);
        session
            .StartCapture()
            .map_err(|e| CaptureError::device_lost(format!("StartCapture: {e}")))?;
        Ok(Self {
            hwnd,
            device,
            item,
            pool,
            session,
            last_content_size: size,
            frame_pool_recreated: false,
            last_resize: None,
        })
    }

    pub fn backend() -> CaptureBackend {
        CaptureBackend::WindowsGraphicsCapture
    }

    pub fn hwnd_raw(&self) -> u64 {
        self.hwnd.0 as u64
    }

    pub fn last_resize_info(&self) -> Option<&ResizeRecoveryInfo> {
        self.last_resize.as_ref()
    }

    pub fn frame_pool_recreated(&self) -> bool {
        self.frame_pool_recreated
    }

    pub fn capture_frame(&mut self, timeout: Duration) -> Result<WgcRawFrame, CaptureError> {
        self.capture_frame_inner(timeout, true)
    }

    fn capture_frame_inner(
        &mut self,
        timeout: Duration,
        allow_static_retry: bool,
    ) -> Result<WgcRawFrame, CaptureError> {
        if unsafe { !IsWindow(Some(self.hwnd)).as_bool() } {
            return Err(CaptureError::target_closed());
        }

        let deadline = Instant::now() + timeout;
        let mut latest: Option<Direct3D11CaptureFrame> = None;
        loop {
            while let Ok(f) = self.pool.TryGetNextFrame() {
                latest = Some(f);
            }
            if latest.is_some() {
                std::thread::sleep(Duration::from_millis(16));
                while let Ok(f) = self.pool.TryGetNextFrame() {
                    latest = Some(f);
                }
                break;
            }
            if Instant::now() >= deadline {
                break;
            }
            std::thread::sleep(Duration::from_millis(10));
        }
        if latest.is_none() && allow_static_retry {
            // Paused / static CS2 content often stops WGC FrameArrived. Recreate the
            // free-threaded pool + session once to force a fresh composition sample.
            self.recreate_pool_and_session()?;
            return self.capture_frame_inner(timeout, false);
        }
        let frame = FrameGuard(latest.ok_or_else(CaptureError::frame_timeout)?);

        let content = frame
            .ContentSize()
            .map_err(|e| CaptureError::copy_failed(e.to_string()))?;

        if content.Width != self.last_content_size.Width
            || content.Height != self.last_content_size.Height
        {
            let old_size = (
                self.last_content_size.Width.max(0) as u32,
                self.last_content_size.Height.max(0) as u32,
            );
            let new_size = (content.Width.max(0) as u32, content.Height.max(0) as u32);
            self.pool
                .Recreate(
                    &self.device.rt_device,
                    DirectXPixelFormat::B8G8R8A8UIntNormalized,
                    2,
                    content,
                )
                .map_err(|e| CaptureError::device_lost(format!("frame pool Recreate: {e}")))?;
            self.last_content_size = content;
            self.frame_pool_recreated = true;
            self.last_resize = Some(ResizeRecoveryInfo {
                frame_pool_recreated: true,
                old_size,
                new_size,
                hwnd_changed: false,
                target_rediscovered: false,
                device_recreated: false,
            });
            // Drop current frame (size may not match new pool); wait for a fresh one.
            drop(frame);
            return self.capture_frame_inner(
                timeout.saturating_sub(Duration::from_millis(50)),
                false,
            );
        }

        let surface = frame
            .Surface()
            .map_err(|e| CaptureError::copy_failed(e.to_string()))?;
        let access: IDirect3DDxgiInterfaceAccess = surface
            .cast()
            .map_err(|e| CaptureError::copy_failed(e.to_string()))?;
        let texture: ID3D11Texture2D = unsafe { access.GetInterface() }
            .map_err(|e| CaptureError::copy_failed(format!("GetInterface: {e}")))?;

        let mut desc = D3D11_TEXTURE2D_DESC::default();
        unsafe { texture.GetDesc(&mut desc) };
        let surface_w = desc.Width;
        let surface_h = desc.Height;
        desc.Usage = D3D11_USAGE_STAGING;
        desc.BindFlags = 0;
        desc.CPUAccessFlags = D3D11_CPU_ACCESS_READ.0 as u32;
        desc.MiscFlags = 0;

        let mut staging_opt: Option<ID3D11Texture2D> = None;
        unsafe {
            self.device
                .device
                .CreateTexture2D(&desc, None, Some(&mut staging_opt))
        }
        .map_err(|e| CaptureError::copy_failed(format!("CreateTexture2D: {e}")))?;
        let staging = staging_opt.ok_or_else(|| CaptureError::copy_failed("staging null"))?;

        unsafe {
            self.device.context.CopyResource(&staging, &texture);
        }

        let mut mapped = D3D11_MAPPED_SUBRESOURCE::default();
        unsafe {
            self.device
                .context
                .Map(&staging, 0, D3D11_MAP_READ, 0, Some(&mut mapped))
        }
        .map_err(|e| CaptureError::copy_failed(format!("Map: {e}")))?;

        let content_w = (content.Width.max(0) as u32).min(surface_w);
        let content_h = (content.Height.max(0) as u32).min(surface_h);
        if content_w == 0 || content_h == 0 {
            unsafe {
                self.device.context.Unmap(&staging, 0);
            }
            return Err(CaptureError::target_zero_size());
        }

        let row_pitch = mapped.RowPitch as usize;
        let mut out = vec![0u8; content_w as usize * content_h as usize * 4];
        unsafe {
            let src = mapped.pData as *const u8;
            for y in 0..content_h as usize {
                let src_row = src.add(y * row_pitch);
                let dst_off = y * content_w as usize * 4;
                std::ptr::copy_nonoverlapping(
                    src_row,
                    out.as_mut_ptr().add(dst_off),
                    content_w as usize * 4,
                );
            }
            self.device.context.Unmap(&staging, 0);
        }

        let qpc = frame.SystemRelativeTime().ok().map(|t| t.Duration as u64);

        Ok(WgcRawFrame {
            width: content_w,
            height: content_h,
            pixels_bgra: out,
            pixel_format: PixelFormat::Bgra8,
            source_timestamp_qpc: qpc,
            content_size_changed: false,
            frame_pool_recreated: self.frame_pool_recreated,
            old_size: self.last_resize.as_ref().map(|r| r.old_size),
            new_size: self.last_resize.as_ref().map(|r| r.new_size),
        })
    }

    fn recreate_pool_and_session(&mut self) -> Result<(), CaptureError> {
        let size = self
            .item
            .Size()
            .map_err(|e| CaptureError::device_lost(e.to_string()))?;
        if size.Width <= 0 || size.Height <= 0 {
            return Err(CaptureError::target_zero_size());
        }
        let pool = PoolGuard(
            Direct3D11CaptureFramePool::CreateFreeThreaded(
                &self.device.rt_device,
                DirectXPixelFormat::B8G8R8A8UIntNormalized,
                2,
                size,
            )
            .map_err(|e| CaptureError::device_lost(format!("recreate CreateFreeThreaded: {e}")))?,
        );
        let session = SessionGuard(
            pool.CreateCaptureSession(&self.item)
                .map_err(|e| CaptureError::device_lost(format!("recreate CreateCaptureSession: {e}")))?,
        );
        let _ = session.SetIsCursorCaptureEnabled(false);
        let _ = session.SetIsBorderRequired(false);
        session
            .StartCapture()
            .map_err(|e| CaptureError::device_lost(format!("recreate StartCapture: {e}")))?;
        // Replace fields; old guards Close on drop.
        self.session = session;
        self.pool = pool;
        self.last_content_size = size;
        self.frame_pool_recreated = true;
        Ok(())
    }
}

impl Drop for WgcCaptureSession {
    fn drop(&mut self) {
        // SessionGuard / PoolGuard Close on drop (LIFO after fields).
        let _ = &self.session;
        let _ = &self.pool;
    }
}

impl CaptureError {
    fn target_closed_detail(detail: String) -> Self {
        Self::new(
            "CAPTURE_TARGET_CLOSED",
            detail,
            Some("Rediscover the CS2 window and retry the capture"),
        )
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn wgc_support_probe_does_not_panic() {
        let _ = wgc_is_supported();
    }
}
