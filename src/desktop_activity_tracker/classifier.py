"""Software classifier based on process name and window title keywords.

Classification rules are driven by config/config.yaml.
"""

# TODO: v0.3.0 - Implement Classifier class
# - Load YAML category rules
# - Match by process_name in category's process_names list
# - Match by window_title against category's title_keywords
# - Browser special handling: title-first matching for Chrome/Edge
# - Default fallback to "other" category
#
# TODO: v0.4.0 - Add is_effective() method
# - interactive_required: idle_seconds <= threshold
# - passive_allowed: always True
