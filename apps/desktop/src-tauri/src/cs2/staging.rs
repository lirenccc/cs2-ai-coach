//! Safe demo staging for NetCon `playdemo`.
//!
//! Original arbitrary Windows paths are never embedded into console commands.

use crate::cs2::error::Cs2Error;
use sha2::{Digest, Sha256};
use std::fs::{self, File};
use std::io::{self, Read, Write};
use std::path::{Component, Path, PathBuf};
use std::time::{Duration, SystemTime};

const MAX_DEMO_BYTES: u64 = 1_073_741_824; // 1 GiB
const DEFAULT_TTL: Duration = Duration::from_secs(24 * 60 * 60);

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct StagedDemo {
    pub source_path: PathBuf,
    pub staged_path: PathBuf,
    /// Safe ASCII basename ending in `.dem` for `ReplayCommand::PlayStagedDemo`.
    pub staged_name: String,
    pub sha256: String,
    pub from_archive: bool,
}

pub struct DemoStagingService {
    root: PathBuf,
    ttl: Duration,
}

impl DemoStagingService {
    pub fn new(root: impl Into<PathBuf>) -> Self {
        let root = root.into();
        // Normalize logical `..` segments from callers (e.g. CARGO_MANIFEST_DIR/../../..).
        let root = normalize_path(&root);
        Self {
            root,
            ttl: DEFAULT_TTL,
        }
    }

    pub fn with_ttl(mut self, ttl: Duration) -> Self {
        self.ttl = ttl;
        self
    }

    pub fn root(&self) -> &Path {
        &self.root
    }

    /// Stage an arbitrary private `.dem` / `.zip` into a SHA-256 safe ASCII name.
    /// Idempotent: re-staging the same content reuses the staged file.
    pub fn stage(&self, source: impl AsRef<Path>) -> Result<StagedDemo, Cs2Error> {
        let source = canonicalize_source(source.as_ref())?;
        fs::create_dir_all(&self.root).map_err(|e| staging_err(format!("mkdir: {e}")))?;

        if source.extension().and_then(|e| e.to_str()).map(|e| e.eq_ignore_ascii_case("zip")) == Some(true)
        {
            return self.stage_zip(&source);
        }
        if source.extension().and_then(|e| e.to_str()).map(|e| e.eq_ignore_ascii_case("dem"))
            != Some(true)
        {
            return Err(staging_err("expected a .dem or .zip source"));
        }

        let sha = sha256_file(&source)?;
        let staged_name = format!("{sha}.dem");
        validate_staged_name(&staged_name)?;
        let staged_path = self.safe_join(&staged_name)?;
        if !staged_path.is_file() {
            copy_file(&source, &staged_path)?;
        }
        Ok(StagedDemo {
            source_path: source,
            staged_path,
            staged_name,
            sha256: sha,
            from_archive: false,
        })
    }

    /// Copy a staged demo into the CS2 `csgo` directory under the same safe name.
    pub fn publish_to_csgo(
        &self,
        staged: &StagedDemo,
        csgo_dir: &Path,
    ) -> Result<PathBuf, Cs2Error> {
        if !csgo_dir.is_dir() {
            return Err(staging_err("csgo directory missing"));
        }
        validate_staged_name(&staged.staged_name)?;
        let canon_csgo = csgo_dir
            .canonicalize()
            .map_err(|e| staging_err(format!("canonicalize csgo: {e}")))?;
        let target = canon_csgo.join(&staged.staged_name);
        if !target.starts_with(&canon_csgo) {
            return Err(staging_err("refusing csgo publish outside csgo dir"));
        }
        if !target.is_file() {
            copy_file(&staged.staged_path, &target)?;
        }
        Ok(target)
    }

    pub fn cleanup_expired(&self) -> Result<usize, Cs2Error> {
        if !self.root.is_dir() {
            return Ok(0);
        }
        let now = SystemTime::now();
        let mut removed = 0usize;
        for entry in fs::read_dir(&self.root).map_err(|e| staging_err(e.to_string()))? {
            let entry = entry.map_err(|e| staging_err(e.to_string()))?;
            let path = entry.path();
            if path.extension().and_then(|e| e.to_str()) != Some("dem") {
                continue;
            }
            let aged = entry
                .metadata()
                .and_then(|m| m.modified())
                .ok()
                .and_then(|m| now.duration_since(m).ok())
                .is_some_and(|age| age > self.ttl);
            if aged {
                fs::remove_file(&path).ok();
                removed += 1;
            }
        }
        Ok(removed)
    }

    fn stage_zip(&self, zip_path: &Path) -> Result<StagedDemo, Cs2Error> {
        let file = File::open(zip_path).map_err(|e| staging_err(e.to_string()))?;
        let mut archive =
            zip::ZipArchive::new(file).map_err(|e| staging_err(format!("zip open: {e}")))?;
        let member_index = select_dem_member(&mut archive)?;
        let mut member = archive
            .by_index(member_index)
            .map_err(|e| staging_err(format!("zip member: {e}")))?;
        if member.size() == 0 || member.size() > MAX_DEMO_BYTES {
            return Err(staging_err("zip demo member size rejected"));
        }

        let mut hasher = Sha256::new();
        let temp = self.root.join(format!(".staging-{}.dem", std::process::id()));
        {
            let mut out =
                File::create(&temp).map_err(|e| staging_err(format!("staging create: {e}")))?;
            let mut buf = [0u8; 1024 * 1024];
            let mut remaining = member.size();
            while remaining > 0 {
                let n = member
                    .read(&mut buf)
                    .map_err(|e| staging_err(format!("zip read: {e}")))?;
                if n == 0 {
                    break;
                }
                let take = n.min(remaining as usize);
                hasher.update(&buf[..take]);
                out.write_all(&buf[..take])
                    .map_err(|e| staging_err(format!("staging write: {e}")))?;
                remaining -= take as u64;
            }
            if remaining != 0 {
                let _ = fs::remove_file(&temp);
                return Err(staging_err("zip member ended before declared size"));
            }
        }

        let sha = hex_encode(hasher.finalize());
        let staged_name = format!("{sha}.dem");
        validate_staged_name(&staged_name)?;
        let staged_path = self.safe_join(&staged_name)?;
        if staged_path.is_file() {
            let _ = fs::remove_file(&temp);
        } else {
            fs::rename(&temp, &staged_path).or_else(|_| {
                copy_file(&temp, &staged_path)?;
                fs::remove_file(&temp).map_err(|e| staging_err(e.to_string()))
            })?;
        }

        Ok(StagedDemo {
            source_path: zip_path.to_path_buf(),
            staged_path,
            staged_name,
            sha256: sha,
            from_archive: true,
        })
    }

    fn safe_join(&self, name: &str) -> Result<PathBuf, Cs2Error> {
        validate_staged_name(name)?;
        // Name is already restricted to ASCII basename characters; never join raw user paths.
        Ok(self.root.join(name))
    }
}

fn normalize_path(path: &Path) -> PathBuf {
    let mut out = PathBuf::new();
    for component in path.components() {
        match component {
            Component::ParentDir => {
                out.pop();
            }
            Component::CurDir => {}
            other => out.push(other.as_os_str()),
        }
    }
    out
}

fn select_dem_member<R: Read + io::Seek>(
    archive: &mut zip::ZipArchive<R>,
) -> Result<usize, Cs2Error> {
    let mut dem_indexes = Vec::new();
    for i in 0..archive.len() {
        let member = archive
            .by_index(i)
            .map_err(|e| staging_err(format!("zip index: {e}")))?;
        let name = member.name().replace('\\', "/");
        if name.split('/').any(|p| p == "..") {
            return Err(staging_err("zip-slip path rejected"));
        }
        if Path::new(&name)
            .components()
            .any(|c| matches!(c, Component::ParentDir | Component::RootDir))
        {
            return Err(staging_err("zip-slip path rejected"));
        }
        if member.is_dir() {
            continue;
        }
        if name.to_ascii_lowercase().ends_with(".dem") {
            dem_indexes.push((i, name));
        }
    }
    match dem_indexes.as_slice() {
        [] => Err(staging_err("zip contains no .dem entry")),
        [only] => Ok(only.0),
        many => {
            // Deterministic policy: prefer `<zipstem>.dem` basename match is handled by caller
            // via sorting; here pick lexicographically smallest basename for stability.
            let mut sorted = many.to_vec();
            sorted.sort_by(|a, b| {
                Path::new(&a.1)
                    .file_name()
                    .cmp(&Path::new(&b.1).file_name())
            });
            // Ambiguous if more than one distinct basename.
            let names: Vec<_> = sorted
                .iter()
                .filter_map(|(_, n)| Path::new(n).file_name().map(|s| s.to_os_string()))
                .collect();
            let unique = {
                let mut u = names.clone();
                u.sort();
                u.dedup();
                u
            };
            if unique.len() != 1 {
                return Err(staging_err(
                    "zip contains multiple ambiguous .dem entries; refuse without explicit policy",
                ));
            }
            Ok(sorted[0].0)
        }
    }
}

fn canonicalize_source(path: &Path) -> Result<PathBuf, Cs2Error> {
    path.canonicalize()
        .map_err(|_| staging_err("demo source does not exist"))
}

fn sha256_file(path: &Path) -> Result<String, Cs2Error> {
    let mut file = File::open(path).map_err(|e| staging_err(e.to_string()))?;
    let mut hasher = Sha256::new();
    let mut buf = [0u8; 1024 * 1024];
    loop {
        let n = file.read(&mut buf).map_err(|e| staging_err(e.to_string()))?;
        if n == 0 {
            break;
        }
        hasher.update(&buf[..n]);
    }
    Ok(hex_encode(hasher.finalize()))
}

fn copy_file(src: &Path, dst: &Path) -> Result<(), Cs2Error> {
    if let Some(parent) = dst.parent() {
        fs::create_dir_all(parent).map_err(|e| staging_err(e.to_string()))?;
    }
    fs::copy(src, dst).map_err(|e| staging_err(format!("copy failed: {e}")))?;
    Ok(())
}

fn validate_staged_name(name: &str) -> Result<(), Cs2Error> {
    if name.is_empty() || name.len() > 128 || !name.ends_with(".dem") {
        return Err(staging_err("invalid staged name"));
    }
    if name.contains("..") || name.contains('/') || name.contains('\\') {
        return Err(staging_err("staged name path traversal rejected"));
    }
    if !name
        .bytes()
        .all(|b| b.is_ascii_alphanumeric() || matches!(b, b'.' | b'_' | b'-'))
    {
        return Err(staging_err("staged name has unsafe characters"));
    }
    Ok(())
}

fn hex_encode(bytes: impl AsRef<[u8]>) -> String {
    bytes
        .as_ref()
        .iter()
        .map(|b| format!("{b:02x}"))
        .collect()
}

fn staging_err(message: impl Into<String>) -> Cs2Error {
    Cs2Error::new(
        "DEMO_STAGING_FAILED",
        message,
        Some("Use a single .dem or a zip with one unambiguous .dem entry"),
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use std::io::Write;
    use zip::write::SimpleFileOptions;
    use zip::ZipWriter;

    #[test]
    fn stages_dem_with_sha_name_idempotently() {
        let dir = tempfile_dir("stage-dem");
        let src = dir.join("source weird name.dem");
        fs::write(&src, b"PBDEMS2\0fixture").unwrap();
        let svc = DemoStagingService::new(dir.join("staging"));
        let first = svc.stage(&src).unwrap();
        let second = svc.stage(&src).unwrap();
        assert_eq!(first.staged_name, second.staged_name);
        assert_eq!(first.sha256, second.sha256);
        assert!(first.staged_name.ends_with(".dem"));
        assert!(first.staged_name.is_ascii());
        assert!(!first.staged_name.contains(' '));
    }

    #[test]
    fn rejects_zip_slip() {
        let dir = tempfile_dir("zip-slip");
        let zip_path = dir.join("evil.zip");
        {
            let file = File::create(&zip_path).unwrap();
            let mut zip = ZipWriter::new(file);
            zip.start_file(
                "../escape.dem",
                SimpleFileOptions::default(),
            )
            .unwrap();
            zip.write_all(b"PBDEMS2").unwrap();
            zip.finish().unwrap();
        }
        let svc = DemoStagingService::new(dir.join("staging"));
        let err = svc.stage(&zip_path).unwrap_err();
        assert_eq!(err.code, "DEMO_STAGING_FAILED");
        assert!(err.message.contains("zip-slip") || err.message.contains("no .dem"));
    }

    #[test]
    fn rejects_ambiguous_multiple_dems() {
        let dir = tempfile_dir("multi-dem");
        let zip_path = dir.join("multi.zip");
        {
            let file = File::create(&zip_path).unwrap();
            let mut zip = ZipWriter::new(file);
            let opts = SimpleFileOptions::default();
            zip.start_file("a.dem", opts).unwrap();
            zip.write_all(b"PBDEMS2a").unwrap();
            zip.start_file("b.dem", opts).unwrap();
            zip.write_all(b"PBDEMS2b").unwrap();
            zip.finish().unwrap();
        }
        let svc = DemoStagingService::new(dir.join("staging"));
        let err = svc.stage(&zip_path).unwrap_err();
        assert!(err.message.contains("ambiguous"));
    }

    #[test]
    fn extracts_single_dem_zip() {
        let dir = tempfile_dir("one-dem");
        let zip_path = dir.join("one.zip");
        {
            let file = File::create(&zip_path).unwrap();
            let mut zip = ZipWriter::new(file);
            zip.start_file("match.dem", SimpleFileOptions::default())
                .unwrap();
            zip.write_all(b"PBDEMS2payload").unwrap();
            zip.finish().unwrap();
        }
        let svc = DemoStagingService::new(dir.join("staging"));
        let staged = svc.stage(&zip_path).unwrap();
        assert!(staged.from_archive);
        assert_eq!(fs::read(&staged.staged_path).unwrap(), b"PBDEMS2payload");
    }

    fn tempfile_dir(label: &str) -> PathBuf {
        let root = std::env::temp_dir().join(format!(
            "cs2coach-staging-{label}-{}",
            std::process::id()
        ));
        let _ = fs::remove_dir_all(&root);
        fs::create_dir_all(&root).unwrap();
        root
    }
}
