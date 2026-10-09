//! P0.5A replay tick-domain calibration (offline Demo + real CS2).
//!
//! Separates command-delivery evidence from replay-position evidence.
//! Never treats NetCon write success as proof of landed tick.
//! Never translates `demo_tick` ↔ `server_tick`.

use crate::cs2::tick::{ReplayTick, ReplayTickDomain};
use serde::{Deserialize, Serialize};
use std::collections::BTreeSet;
use std::path::Path;

/// Build-specific calibration contract version. Invalidate / re-run when CS2 or
/// fixture semantics change. See `docs/spikes/replay/P0_5A_TICK_CALIBRATION.md`.
pub const REPLAY_SEMANTICS_VERSION: &str = "p0.5a-2026-10-10";

pub const SELECTION_ALGORITHM: &str = "p0_5a_v1";

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum CalibrationDecision {
    DemoTickAuthoritative,
    ServerTickAuthoritative,
    /// Regions / repetitions disagree — keep production seek UNVERIFIED.
    Inconsistent,
    /// Insufficient position evidence (must not become a false success).
    Inconclusive,
}

impl CalibrationDecision {
    pub fn as_error_code(self) -> Option<&'static str> {
        match self {
            Self::Inconsistent => Some("REPLAY_TICK_DOMAIN_INCONSISTENT"),
            Self::Inconclusive => Some("REPLAY_TICK_DOMAIN_INCONCLUSIVE"),
            Self::DemoTickAuthoritative | Self::ServerTickAuthoritative => None,
        }
    }

    pub fn authoritative_domain(self) -> Option<ReplayTickDomain> {
        match self {
            Self::DemoTickAuthoritative => Some(ReplayTickDomain::DemoTick),
            Self::ServerTickAuthoritative => Some(ReplayTickDomain::ServerTick),
            Self::Inconsistent | Self::Inconclusive => None,
        }
    }
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum VisualVerification {
    CorrectEvent,
    Early,
    Late,
    WrongRound,
    NotObservable,
}

#[derive(Debug, Clone, Copy, PartialEq, Eq, Serialize, Deserialize)]
#[serde(rename_all = "snake_case")]
pub enum VerificationPrecision {
    EngineReported,
    Visual,
    None,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct CalibrationAnchor {
    pub anchor_id: String,
    pub category: String,
    pub round_id: u32,
    pub event_type: String,
    pub event_index: u64,
    pub demo_tick: u64,
    pub server_tick: u64,
    pub round_start_demo_tick: u64,
    pub round_relative_order: u64,
    pub attacker_controller_id: Option<String>,
    pub victim_controller_id: Option<String>,
    pub attacker_pawn_handle: Option<i64>,
    pub victim_pawn_handle: Option<i64>,
    pub weapon: Option<String>,
    pub bomb_site: Option<i64>,
    pub headshot: Option<bool>,
    pub related_bot_takeover_demo_tick: Option<u64>,
    pub verification_cue: String,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct CalibrationAnchorSet {
    pub fixture_sha256: String,
    pub map_name: String,
    pub server_start_tick: u64,
    pub playback_ticks: u64,
    pub verified_tick_rate: f64,
    pub playback_time_seconds: f64,
    pub timing_source: String,
    pub round_freeze_end_demo_ticks: Vec<u64>,
    pub side_transition_round_id: u32,
    pub selection_algorithm: String,
    pub anchors: Vec<CalibrationAnchor>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct CandidateEvent {
    pub event_index: u64,
    pub event_type: String,
    pub demo_tick: u64,
    pub server_tick: u64,
    pub attacker_userid: Option<u32>,
    pub victim_userid: Option<u32>,
    pub attacker_pawn: Option<i64>,
    pub victim_pawn: Option<i64>,
    pub weapon: Option<String>,
    pub bomb_site: Option<i64>,
    pub headshot: Option<bool>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct CommandDeliveryEvidence {
    pub write_ok: bool,
    pub raw_response_preview: String,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct ReplayPositionEvidence {
    pub engine_reported_tick: Option<u64>,
    pub engine_reported_raw: Option<String>,
    pub verification: Option<VisualVerification>,
    pub verification_precision: VerificationPrecision,
    pub offset_ticks: Option<i64>,
    pub settle_duration_ms: u64,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct CalibrationSeekTest {
    pub candidate_domain: ReplayTickDomain,
    pub candidate_value: u64,
    pub repeat: u32,
    pub command_delivery: CommandDeliveryEvidence,
    pub replay_position: ReplayPositionEvidence,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct CalibrationAnchorResult {
    pub anchor_id: String,
    pub demo_tick: u64,
    pub server_tick: u64,
    pub tests: Vec<CalibrationSeekTest>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct PreRollTrial {
    pub anchor_id: String,
    pub requested_pre_roll_seconds: f64,
    pub ticks_per_second: f64,
    pub round_start_demo_tick: u64,
    pub anchor_replay_tick: u64,
    pub pre_roll_replay_tick: u64,
    pub clamped_to_round_start: bool,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct CalibrationResultDocument {
    pub replay_semantics_version: String,
    pub cs2_patch_version: Option<String>,
    pub cs2_client_version: Option<String>,
    pub steam_buildid: Option<String>,
    pub fixture_sha256: String,
    pub app_commit: Option<String>,
    pub calibration_timestamp_utc: String,
    pub decision: CalibrationDecision,
    pub decision_error_code: Option<String>,
    pub anchors: Vec<CalibrationAnchorResult>,
    pub pre_roll_trials: Vec<PreRollTrial>,
    pub demo_info_reliable: bool,
    pub pause_at_server_tick: PauseAtServerTickFinding,
    pub notes: Vec<String>,
}

#[derive(Debug, Clone, PartialEq, Serialize, Deserialize)]
pub struct PauseAtServerTickFinding {
    pub command_accepted_write: bool,
    pub reliable_pause_at_event: Option<bool>,
    pub raw_response_preview: Option<String>,
    pub notes: String,
}

/// Pre-roll in the *same* replay domain as the calibrated seek clock.
/// Uses caller-supplied ticks/second — never assumes a global 64 Hz rate.
pub fn pre_roll_tick(
    anchor_tick: u64,
    round_start_tick: u64,
    seconds: f64,
    ticks_per_second: f64,
) -> Result<u64, String> {
    if round_start_tick > anchor_tick {
        return Err("round_start_tick cannot be after anchor_tick".into());
    }
    if !seconds.is_finite() || seconds < 0.0 {
        return Err("seconds must be finite and non-negative".into());
    }
    if !ticks_per_second.is_finite() || ticks_per_second <= 0.0 {
        return Err("ticks_per_second must be finite and positive".into());
    }
    let delta = (seconds * ticks_per_second).round() as u64;
    Ok(anchor_tick.saturating_sub(delta).max(round_start_tick))
}

pub fn load_anchor_set(path: impl AsRef<Path>) -> Result<CalibrationAnchorSet, String> {
    let text = std::fs::read_to_string(path.as_ref()).map_err(|e| e.to_string())?;
    let set: CalibrationAnchorSet =
        serde_json::from_str(&text).map_err(|e| format!("invalid anchor fixture: {e}"))?;
    validate_anchor_set(&set)?;
    Ok(set)
}

pub fn validate_anchor_set(set: &CalibrationAnchorSet) -> Result<(), String> {
    if set.anchors.len() < 5 {
        return Err("need at least 5 anchors".into());
    }
    let cats: BTreeSet<_> = set.anchors.iter().map(|a| a.category.as_str()).collect();
    for required in [
        "early_match",
        "middle_match",
        "late_match",
        "after_halftime",
        "near_bot_takeover",
    ] {
        if !cats.contains(required) {
            return Err(format!("missing required category {required}"));
        }
    }
    for a in &set.anchors {
        if a.demo_tick == a.server_tick {
            return Err(format!(
                "anchor {} has identical demo/server ticks — fixture clocks must differ",
                a.anchor_id
            ));
        }
        assert_redacted_ids(a)?;
    }
    Ok(())
}

fn assert_redacted_ids(a: &CalibrationAnchor) -> Result<(), String> {
    for id in [&a.attacker_controller_id, &a.victim_controller_id]
        .into_iter()
        .flatten()
    {
        let ok = id.starts_with('C')
            && id.len() > 1
            && id[1..].chars().all(|c| c.is_ascii_digit())
            && id[1..].parse::<u32>().is_ok();
        if !ok {
            return Err(format!(
                "controller id must be redacted C<userid>, got {id}"
            ));
        }
    }
    let blob = serde_json::to_string(a).unwrap_or_default().to_ascii_lowercase();
    if blob.contains("steamid") {
        return Err("anchor must not contain steam ids".into());
    }
    Ok(())
}

/// Deterministic anchor selection used to produce the committed redacted fixture.
pub fn select_anchors_p0_5a_v1(
    events: &[CandidateEvent],
    freeze_ends: &[u64],
    playback_ticks: u64,
    side_transition_round_id: u32,
) -> Result<Vec<CalibrationAnchor>, String> {
    if freeze_ends.is_empty() {
        return Err("freeze_ends required".into());
    }

    let round_of = |demo_tick: u64| -> u32 {
        let mut rid = 0u32;
        for (i, ft) in freeze_ends.iter().enumerate() {
            if demo_tick >= *ft {
                rid = (i as u32) + 1;
            } else {
                break;
            }
        }
        rid
    };

    let build = |event: &CandidateEvent,
                 anchor_id: &str,
                 category: &str,
                 related_bot: Option<u64>|
     -> CalibrationAnchor {
        let rid = round_of(event.demo_tick);
        let start = if rid == 0 {
            0
        } else {
            freeze_ends[(rid as usize) - 1]
        };
        CalibrationAnchor {
            anchor_id: anchor_id.into(),
            category: category.into(),
            round_id: rid,
            event_type: event.event_type.clone(),
            event_index: event.event_index,
            demo_tick: event.demo_tick,
            server_tick: event.server_tick,
            round_start_demo_tick: start,
            round_relative_order: event.demo_tick.saturating_sub(start),
            attacker_controller_id: event.attacker_userid.map(|u| format!("C{u}")),
            victim_controller_id: event.victim_userid.map(|u| format!("C{u}")),
            attacker_pawn_handle: event.attacker_pawn,
            victim_pawn_handle: event.victim_pawn,
            weapon: event.weapon.clone(),
            bomb_site: event.bomb_site,
            headshot: event.headshot,
            related_bot_takeover_demo_tick: related_bot,
            verification_cue: format!(
                "{} @ demo_tick {} / server_tick {}",
                event.event_type, event.demo_tick, event.server_tick
            ),
        }
    };

    let first = |pred: &dyn Fn(&CandidateEvent) -> bool| -> Option<&CandidateEvent> {
        events.iter().find(|e| pred(e))
    };

    let mut out = Vec::new();

    let early = first(&|e| e.event_type == "bomb_planted" && round_of(e.demo_tick) <= 3)
        .ok_or("missing early bomb_planted")?;
    out.push(build(early, "A01_early_plant", "early_match", None));

    let defuse = first(&|e| e.event_type == "bomb_defused").ok_or("missing bomb_defused")?;
    out.push(build(defuse, "A02_mid_defuse", "middle_match", None));

    let bot = first(&|e| {
        e.event_type == "bot_takeover" && (5..=10).contains(&round_of(e.demo_tick))
    })
    .ok_or("missing bot_takeover")?;
    let near = first(&|e| {
        e.event_type == "player_death"
            && e.demo_tick > bot.demo_tick
            && e.demo_tick <= bot.demo_tick + 2500
    })
    .ok_or("missing death near bot_takeover")?;
    out.push(build(
        near,
        "A03_near_bot_death",
        "near_bot_takeover",
        Some(bot.demo_tick),
    ));

    let post = first(&|e| {
        e.event_type == "bomb_exploded" && round_of(e.demo_tick) >= side_transition_round_id
    })
    .ok_or("missing post-halftime bomb_exploded")?;
    out.push(build(
        post,
        "A04_post_halftime_explode",
        "after_halftime",
        None,
    ));

    let thresh = playback_ticks * 2 / 3;
    let late = first(&|e| {
        e.event_type == "player_death"
            && e.demo_tick >= thresh
            && e.weapon.as_deref() == Some("awp")
    })
    .or_else(|| first(&|e| e.event_type == "player_death" && e.demo_tick >= thresh))
    .ok_or("missing late death")?;
    out.push(build(late, "A05_late_death", "late_match", None));

    let mid = first(&|e| {
        e.event_type == "player_death"
            && round_of(e.demo_tick) == 8
            && e.weapon.as_deref() == Some("ak47")
            && e.headshot == Some(true)
    })
    .or_else(|| {
        first(&|e| e.event_type == "player_death" && (7..=9).contains(&round_of(e.demo_tick)))
    })
    .ok_or("missing mid death")?;
    out.push(build(mid, "A06_mid_ak_hs", "middle_match", None));

    out.sort_by_key(|a| a.demo_tick);
    Ok(out)
}

/// Decide authoritative domain from completed seek observations.
///
/// A domain "wins" an anchor only when at least one repeat for that domain has
/// `verification == CorrectEvent` (or engine-reported offset within tolerance)
/// and the other domain does **not**.
pub fn decide_domain(
    anchors: &[CalibrationAnchorResult],
    engine_tolerance_ticks: u64,
) -> CalibrationDecision {
    if anchors.is_empty() {
        return CalibrationDecision::Inconclusive;
    }

    let mut demo_wins = 0u32;
    let mut server_wins = 0u32;
    let mut conflicts = 0u32;
    let mut judged = 0u32;

    for anchor in anchors {
        let demo_ok = domain_lands(anchor, ReplayTickDomain::DemoTick, engine_tolerance_ticks);
        let server_ok = domain_lands(anchor, ReplayTickDomain::ServerTick, engine_tolerance_ticks);
        match (demo_ok, server_ok) {
            (None, None) => {}
            (Some(true), Some(false)) => {
                judged += 1;
                demo_wins += 1;
            }
            (Some(false), Some(true)) => {
                judged += 1;
                server_wins += 1;
            }
            (Some(true), Some(true)) | (Some(false), Some(false)) => {
                judged += 1;
                conflicts += 1;
            }
            (Some(true), None) => {
                // One domain confirmed; other unobserved — count as provisional win
                // only when every anchor agrees (checked via demo_wins == judged).
                judged += 1;
                demo_wins += 1;
            }
            (None, Some(true)) => {
                judged += 1;
                server_wins += 1;
            }
            (Some(false), None) | (None, Some(false)) => {
                judged += 1;
                // Failure without a contrasting success → does not elect a domain.
            }
        }
    }

    if judged == 0 {
        return CalibrationDecision::Inconclusive;
    }
    if conflicts > 0 {
        return CalibrationDecision::Inconsistent;
    }
    if demo_wins > 0 && server_wins == 0 && demo_wins == judged {
        return CalibrationDecision::DemoTickAuthoritative;
    }
    if server_wins > 0 && demo_wins == 0 && server_wins == judged {
        return CalibrationDecision::ServerTickAuthoritative;
    }
    if demo_wins > 0 && server_wins > 0 {
        return CalibrationDecision::Inconsistent;
    }
    CalibrationDecision::Inconclusive
}

fn domain_lands(
    anchor: &CalibrationAnchorResult,
    domain: ReplayTickDomain,
    engine_tolerance_ticks: u64,
) -> Option<bool> {
    let tests: Vec<_> = anchor
        .tests
        .iter()
        .filter(|t| t.candidate_domain == domain)
        .collect();
    if tests.is_empty() {
        return None;
    }

    let mut any_evidence = false;
    let mut all_good = true;
    for t in tests {
        match evaluate_landing(t, anchor, domain, engine_tolerance_ticks) {
            None => {}
            Some(true) => any_evidence = true,
            Some(false) => {
                any_evidence = true;
                all_good = false;
            }
        }
    }
    if !any_evidence {
        return None;
    }
    Some(all_good)
}

fn evaluate_landing(
    test: &CalibrationSeekTest,
    anchor: &CalibrationAnchorResult,
    _domain: ReplayTickDomain,
    engine_tolerance_ticks: u64,
) -> Option<bool> {
    // Command delivery alone is never position proof.
    if !test.command_delivery.write_ok {
        return Some(false);
    }
    let pos = &test.replay_position;
    // Prefer structured skip report embedded in raw engine text when present.
    if let Some(raw) = pos.engine_reported_raw.as_deref() {
        if let Some(report) = parse_demo_skip_report(raw) {
            return Some(engine_report_matches_anchor(
                &report,
                anchor.demo_tick,
                anchor.server_tick,
                engine_tolerance_ticks,
            ));
        }
    }
    if let Some(report) = parse_demo_skip_report(&test.command_delivery.raw_response_preview) {
        return Some(engine_report_matches_anchor(
            &report,
            anchor.demo_tick,
            anchor.server_tick,
            engine_tolerance_ticks,
        ));
    }
    // Bare reported tick is interpreted as engine demo-tick position.
    if let Some(reported) = pos.engine_reported_tick {
        return Some(reported.abs_diff(anchor.demo_tick) <= engine_tolerance_ticks);
    }
    match pos.verification {
        Some(VisualVerification::CorrectEvent) => Some(true),
        Some(VisualVerification::Early)
        | Some(VisualVerification::Late)
        | Some(VisualVerification::WrongRound) => Some(false),
        Some(VisualVerification::NotObservable) | None => None,
    }
}

/// Engine line observed on this build after `demo_gototick`:
/// `Demo Skipping: skipping to demo tick 4354 (game tick 8133) ...`
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct EngineSkipReport {
    pub demo_tick: u64,
    pub game_tick: Option<u64>,
}

/// Best-effort parse of engine seek acknowledgement. Never fabricates.
pub fn parse_demo_skip_report(raw: &str) -> Option<EngineSkipReport> {
    let lower = raw.to_ascii_lowercase();
    let marker = "skipping to demo tick";
    let idx = lower.find(marker)?;
    let after = &raw[idx + marker.len()..];
    let demo_tick = first_integer_token(after)?;
    let game_tick = lower[idx..]
        .find("game tick")
        .and_then(|rel| first_integer_token(&raw[idx + rel + "game tick".len()..]));
    Some(EngineSkipReport {
        demo_tick,
        game_tick,
    })
}

/// True when the engine report places playback at the anchor's dual-clock pair.
pub fn engine_report_matches_anchor(
    report: &EngineSkipReport,
    demo_tick: u64,
    server_tick: u64,
    tolerance: u64,
) -> bool {
    if report.demo_tick.abs_diff(demo_tick) > tolerance {
        return false;
    }
    match report.game_tick {
        Some(g) => g.abs_diff(server_tick) <= tolerance,
        None => true,
    }
}

/// Best-effort parse of `demo_info` console text for a current tick.
/// Returns `None` when empty or unparseable — never fabricates.
pub fn parse_demo_info_tick(raw: &str) -> Option<u64> {
    if raw.trim().is_empty() {
        return None;
    }
    if let Some(skip) = parse_demo_skip_report(raw) {
        return Some(skip.demo_tick);
    }
    // Prefer explicit key=value / key: value forms over bare integers.
    let lower = raw.to_ascii_lowercase();
    for key in [
        "current tick",
        "playback tick",
        "gototick",
        "server tick",
    ] {
        if let Some(idx) = lower.find(key) {
            let after = &raw[idx + key.len()..];
            if let Some(n) = first_integer_token(after) {
                return Some(n);
            }
        }
    }
    None
}

fn first_integer_token(s: &str) -> Option<u64> {
    let mut digits = String::new();
    let mut started = false;
    for c in s.chars() {
        if c.is_ascii_digit() {
            started = true;
            digits.push(c);
            if digits.len() > 12 {
                break;
            }
        } else if started {
            break;
        } else if c == '=' || c == ':' || c.is_whitespace() || c == '#' {
            continue;
        } else if !started {
            // skip a short amount of noise before digits
            if digits.is_empty() && !c.is_ascii_alphanumeric() {
                continue;
            }
            if !c.is_ascii_digit() && c != '=' && c != ':' {
                // allow small gap
                if s.chars().take(16).any(|x| x.is_ascii_digit()) {
                    continue;
                }
                return None;
            }
        }
    }
    if digits.is_empty() {
        None
    } else {
        digits.parse().ok()
    }
}

pub fn redact_console_preview(raw: &str, max_chars: usize) -> String {
    let flat: String = raw
        .chars()
        .map(|c| if c.is_control() { ' ' } else { c })
        .collect();
    // Strip obvious Steam userdata path segments and long digit runs that look like account ids.
    let mut out = flat;
    if let Some(idx) = out.find("userdata\\") {
        let end = out[idx..]
            .find(' ')
            .map(|i| idx + i)
            .unwrap_or(out.len().min(idx + 48));
        out.replace_range(idx..end, "userdata\\<ACCOUNT>");
    }
    if let Some(idx) = out.find("userdata/") {
        let end = out[idx..]
            .find(' ')
            .map(|i| idx + i)
            .unwrap_or(out.len().min(idx + 48));
        out.replace_range(idx..end, "userdata/<ACCOUNT>");
    }
    out.chars().take(max_chars).collect()
}

pub fn operator_instruction(anchor: &CalibrationAnchor, candidate: ReplayTick) -> String {
    format!(
        "Anchor {}\nExpected round: {}\nExpected event: {}\nExpected visible cue: {}\nCandidate supplied: {:?} {}\n",
        anchor.anchor_id,
        anchor.round_id,
        anchor.event_type,
        anchor.verification_cue,
        candidate.domain,
        candidate.value
    )
}

pub fn default_anchors_fixture_path() -> std::path::PathBuf {
    std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../..")
        .join("docs/spikes/replay/fixtures/tick_calibration_anchors.redacted.json")
}

pub fn default_results_fixture_path() -> std::path::PathBuf {
    std::path::PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .join("../../..")
        .join("docs/spikes/replay/fixtures/tick_calibration.redacted.json")
}

#[cfg(test)]
mod tests {
    use super::*;

    fn sample_events() -> (Vec<CandidateEvent>, Vec<u64>) {
        let freeze: Vec<u64> = vec![
            1181, 5661, 9330, 18915, 25326, 31605, 36503, 43510, 49894, 56467, 64263, 68735,
            75147, 80855, 88090, 95529, 104105, 110792,
        ];
        let events = vec![
            CandidateEvent {
                event_index: 1,
                event_type: "bomb_planted".into(),
                demo_tick: 4354,
                server_tick: 8133,
                attacker_userid: None,
                victim_userid: Some(10),
                attacker_pawn: None,
                victim_pawn: Some(1),
                weapon: None,
                bomb_site: Some(945),
                headshot: None,
            },
            CandidateEvent {
                event_index: 2,
                event_type: "bot_takeover".into(),
                demo_tick: 33717,
                server_tick: 37496,
                attacker_userid: None,
                victim_userid: Some(3),
                attacker_pawn: None,
                victim_pawn: Some(2),
                weapon: None,
                bomb_site: None,
                headshot: None,
            },
            CandidateEvent {
                event_index: 3,
                event_type: "player_death".into(),
                demo_tick: 34176,
                server_tick: 37954,
                attacker_userid: Some(5),
                victim_userid: Some(3),
                attacker_pawn: Some(3),
                victim_pawn: Some(2),
                weapon: Some("awp_vip".into()),
                bomb_site: None,
                headshot: Some(true),
            },
            CandidateEvent {
                event_index: 4,
                event_type: "bomb_defused".into(),
                demo_tick: 42294,
                server_tick: 46073,
                attacker_userid: None,
                victim_userid: Some(8),
                attacker_pawn: None,
                victim_pawn: Some(4),
                weapon: None,
                bomb_site: Some(944),
                headshot: None,
            },
            CandidateEvent {
                event_index: 5,
                event_type: "player_death".into(),
                demo_tick: 47548,
                server_tick: 51326,
                attacker_userid: Some(10),
                victim_userid: Some(4),
                attacker_pawn: Some(5),
                victim_pawn: Some(6),
                weapon: Some("ak47".into()),
                bomb_site: None,
                headshot: Some(true),
            },
            CandidateEvent {
                event_index: 6,
                event_type: "bomb_exploded".into(),
                demo_tick: 79639,
                server_tick: 83418,
                attacker_userid: None,
                victim_userid: Some(4),
                attacker_pawn: None,
                victim_pawn: Some(7),
                weapon: None,
                bomb_site: Some(945),
                headshot: None,
            },
            CandidateEvent {
                event_index: 7,
                event_type: "player_death".into(),
                demo_tick: 88430,
                server_tick: 92208,
                attacker_userid: Some(6),
                victim_userid: Some(10),
                attacker_pawn: Some(8),
                victim_pawn: Some(9),
                weapon: Some("awp".into()),
                bomb_site: None,
                headshot: Some(false),
            },
        ];
        (events, freeze)
    }

    #[test]
    fn committed_anchors_load_and_validate() {
        let set = load_anchor_set(default_anchors_fixture_path()).expect("anchors fixture");
        assert_eq!(set.selection_algorithm, SELECTION_ALGORITHM);
        assert!(set.anchors.len() >= 5);
        assert_eq!(
            set.fixture_sha256,
            "d873502ed8a1df0cd0f919568261e14b92a04e1ca44cd60e84dcec64748a01ec"
        );
    }

    #[test]
    fn selection_is_deterministic() {
        let (events, freeze) = sample_events();
        let a = select_anchors_p0_5a_v1(&events, &freeze, 115418, 13).unwrap();
        let b = select_anchors_p0_5a_v1(&events, &freeze, 115418, 13).unwrap();
        assert_eq!(a, b);
        assert_eq!(a.len(), 6);
        assert_eq!(a[0].anchor_id, "A01_early_plant");
        assert_eq!(a[0].demo_tick, 4354);
        assert_eq!(a[0].server_tick, 8133);
    }

    #[test]
    fn redaction_rejects_names_shaped_ids() {
        let mut set = load_anchor_set(default_anchors_fixture_path()).unwrap();
        set.anchors[0].attacker_controller_id = Some("PlayerFoo".into());
        assert!(validate_anchor_set(&set).is_err());
    }

    #[test]
    fn pre_roll_uses_supplied_timing_and_clamps() {
        let t = pre_roll_tick(2000, 900, 2.0, 64.0).unwrap();
        assert_eq!(t, 2000 - 128);
        let clamped = pre_roll_tick(950, 900, 5.0, 64.0).unwrap();
        assert_eq!(clamped, 900);
        assert!(pre_roll_tick(100, 200, 1.0, 64.0).is_err());
        // no cross-round: clamp keeps us at round start, never below it
        assert!(clamped >= 900);
    }

    #[test]
    fn pre_roll_does_not_assume_global_64() {
        let t = pre_roll_tick(10_000, 0, 1.0, 128.0).unwrap();
        assert_eq!(t, 10_000 - 128);
    }

    #[test]
    fn decide_unanimous_demo() {
        let anchors = vec![result_pair(
            "A1",
            100,
            4000,
            Some(VisualVerification::CorrectEvent),
            Some(VisualVerification::WrongRound),
        )];
        assert_eq!(
            decide_domain(&anchors, 32),
            CalibrationDecision::DemoTickAuthoritative
        );
    }

    #[test]
    fn decide_unanimous_server() {
        let anchors = vec![result_pair(
            "A1",
            100,
            4000,
            Some(VisualVerification::WrongRound),
            Some(VisualVerification::CorrectEvent),
        )];
        assert_eq!(
            decide_domain(&anchors, 32),
            CalibrationDecision::ServerTickAuthoritative
        );
    }

    #[test]
    fn decide_inconsistent() {
        let anchors = vec![
            result_pair(
                "A1",
                100,
                4000,
                Some(VisualVerification::CorrectEvent),
                Some(VisualVerification::WrongRound),
            ),
            result_pair(
                "A2",
                200,
                4200,
                Some(VisualVerification::WrongRound),
                Some(VisualVerification::CorrectEvent),
            ),
        ];
        assert_eq!(
            decide_domain(&anchors, 32),
            CalibrationDecision::Inconsistent
        );
        assert_eq!(
            CalibrationDecision::Inconsistent.as_error_code(),
            Some("REPLAY_TICK_DOMAIN_INCONSISTENT")
        );
    }

    #[test]
    fn missing_observation_is_not_success() {
        let anchors = vec![result_pair("A1", 100, 4000, None, None)];
        assert_eq!(
            decide_domain(&anchors, 32),
            CalibrationDecision::Inconclusive
        );
        let anchors = vec![result_pair(
            "A1",
            100,
            4000,
            Some(VisualVerification::NotObservable),
            Some(VisualVerification::NotObservable),
        )];
        assert_eq!(
            decide_domain(&anchors, 32),
            CalibrationDecision::Inconclusive
        );
    }

    #[test]
    fn write_ok_alone_is_not_position_proof() {
        let mut anchor = result_pair("A1", 100, 4000, None, None);
        for t in &mut anchor.tests {
            t.command_delivery.write_ok = true;
            t.replay_position.verification = None;
            t.replay_position.engine_reported_tick = None;
        }
        assert_eq!(
            decide_domain(&[anchor], 32),
            CalibrationDecision::Inconclusive
        );
    }

    #[test]
    fn result_json_roundtrip() {
        let doc = CalibrationResultDocument {
            replay_semantics_version: REPLAY_SEMANTICS_VERSION.into(),
            cs2_patch_version: Some("1.41.9.0".into()),
            cs2_client_version: Some("2000930".into()),
            steam_buildid: Some("25815307".into()),
            fixture_sha256: "abc".into(),
            app_commit: None,
            calibration_timestamp_utc: "2026-10-10T00:00:00Z".into(),
            decision: CalibrationDecision::Inconclusive,
            decision_error_code: Some("REPLAY_TICK_DOMAIN_INCONCLUSIVE".into()),
            anchors: vec![],
            pre_roll_trials: vec![],
            demo_info_reliable: false,
            pause_at_server_tick: PauseAtServerTickFinding {
                command_accepted_write: false,
                reliable_pause_at_event: None,
                raw_response_preview: None,
                notes: "not run".into(),
            },
            notes: vec![],
        };
        let s = serde_json::to_string_pretty(&doc).unwrap();
        let back: CalibrationResultDocument = serde_json::from_str(&s).unwrap();
        assert_eq!(back.decision, CalibrationDecision::Inconclusive);
    }

    #[test]
    fn parse_demo_info_empty_is_none() {
        assert_eq!(parse_demo_info_tick(""), None);
        assert_eq!(parse_demo_info_tick("   "), None);
        assert_eq!(
            parse_demo_info_tick("Current tick: 12345 something"),
            Some(12345)
        );
        // steam noise without tick key must not invent
        assert_eq!(
            parse_demo_info_tick("SteamID is [U:1:1] AppID is 730"),
            None
        );
    }

    #[test]
    fn parse_demo_skip_report_from_engine() {
        let raw = "Demo Skipping: skipping to demo tick 4354 (game tick 8133) from full packet 3840 (7619).  Current playback is 0 (3779)";
        let report = parse_demo_skip_report(raw).unwrap();
        assert_eq!(report.demo_tick, 4354);
        assert_eq!(report.game_tick, Some(8133));
        assert!(engine_report_matches_anchor(&report, 4354, 8133, 0));
        assert!(!engine_report_matches_anchor(&report, 8133, 11912, 0));
    }

    #[test]
    fn engine_skip_elects_demo_domain() {
        let raw = "Demo Skipping: skipping to demo tick 4354 (game tick 8133)";
        let mut anchor = result_pair("A1", 4354, 8133, None, None);
        anchor.tests[0].command_delivery.raw_response_preview = raw.into();
        anchor.tests[0].replay_position.verification_precision =
            VerificationPrecision::EngineReported;
        // Server candidate seeks to wrong demo tick (empty / mismatch).
        anchor.tests[1].command_delivery.raw_response_preview =
            "Demo Skipping: skipping to demo tick 8133 (game tick 11912)".into();
        assert_eq!(
            decide_domain(&[anchor], 32),
            CalibrationDecision::DemoTickAuthoritative
        );
    }

    #[test]
    fn domains_remain_distinct_in_candidates() {
        let d = ReplayTick::demo(1);
        let s = ReplayTick::server(1);
        assert_ne!(d, s);
        assert_eq!(d.domain, ReplayTickDomain::DemoTick);
        assert_eq!(s.domain, ReplayTickDomain::ServerTick);
    }

    fn result_pair(
        id: &str,
        demo: u64,
        server: u64,
        demo_v: Option<VisualVerification>,
        server_v: Option<VisualVerification>,
    ) -> CalibrationAnchorResult {
        CalibrationAnchorResult {
            anchor_id: id.into(),
            demo_tick: demo,
            server_tick: server,
            tests: vec![
                CalibrationSeekTest {
                    candidate_domain: ReplayTickDomain::DemoTick,
                    candidate_value: demo,
                    repeat: 1,
                    command_delivery: CommandDeliveryEvidence {
                        write_ok: true,
                        raw_response_preview: String::new(),
                    },
                    replay_position: ReplayPositionEvidence {
                        engine_reported_tick: None,
                        engine_reported_raw: None,
                        verification: demo_v,
                        verification_precision: if demo_v.is_some() {
                            VerificationPrecision::Visual
                        } else {
                            VerificationPrecision::None
                        },
                        offset_ticks: None,
                        settle_duration_ms: 2000,
                    },
                },
                CalibrationSeekTest {
                    candidate_domain: ReplayTickDomain::ServerTick,
                    candidate_value: server,
                    repeat: 1,
                    command_delivery: CommandDeliveryEvidence {
                        write_ok: true,
                        raw_response_preview: String::new(),
                    },
                    replay_position: ReplayPositionEvidence {
                        engine_reported_tick: None,
                        engine_reported_raw: None,
                        verification: server_v,
                        verification_precision: if server_v.is_some() {
                            VerificationPrecision::Visual
                        } else {
                            VerificationPrecision::None
                        },
                        offset_ticks: None,
                        settle_duration_ms: 2000,
                    },
                },
            ],
        }
    }
}
