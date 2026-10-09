//! Desktop bootstrap constants.

pub fn app_phase() -> &'static str {
    "P0.5A"
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn phase_label_is_stable() {
        assert_eq!(app_phase(), "P0.5A");
    }
}
