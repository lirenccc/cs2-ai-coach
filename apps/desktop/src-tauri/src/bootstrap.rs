//! Desktop bootstrap constants.

pub fn app_phase() -> &'static str {
    "P1.3"
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn phase_label_is_stable() {
        assert_eq!(app_phase(), "P1.3");
    }
}
