//! Desktop bootstrap constants. No CS2 / capture / AI wiring in P0.1.

pub fn app_phase() -> &'static str {
    "P0.1"
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn phase_label_is_stable() {
        assert_eq!(app_phase(), "P0.1");
    }
}
