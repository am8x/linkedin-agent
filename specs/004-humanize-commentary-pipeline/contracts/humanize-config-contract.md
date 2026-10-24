# Contract: HumanizeAI Configuration Schema

**File**: `config.yaml`  
**Configuration Section**: `humanize:`

---

## 1. YAML Configuration Schema

```yaml
# ---------------------------------------------------------------------------
# HumanizeAI Browser Automation Settings (Playwright)
# ---------------------------------------------------------------------------
humanize:
  enabled: true                        # Master toggle to enable/disable HumanizeAI processing
  headless: true                       # Headless Chromium mode (set false for visual DOM debugging)
  timeout_seconds: 30.0                # Total timeout per page operation and network idle wait
  detector_url: "https://www.humanizeai.pro/detector"  # Target AI detector tool URL
  humanize_url: "https://www.humanizeai.pro/"          # Target Humanizer rewriting tool URL
  auto_retry: true                     # Perform 1 automatic retry on transient timeouts
  retry_cooldown_seconds: 2.0          # Pause duration before executing retry attempt
```

---

## 2. Environment Variable Overrides

Any YAML setting can be overridden at runtime via uppercase environment variables with prefix `HUMANIZE_`:

| Environment Variable | Target Key | Example Value | Description |
|---|---|---|---|
| `HUMANIZE_ENABLED` | `humanize.enabled` | `false` | Disable humanization (useful in CI or test suites) |
| `HUMANIZE_HEADLESS` | `humanize.headless` | `false` | Launch visible browser window for debugging |
| `HUMANIZE_TIMEOUT_SECONDS` | `humanize.timeout_seconds` | `45.0` | Extend timeout on slow network connections |

---

## 3. Validation Rules (Pydantic v2)

1. `timeout_seconds`: Must be between `5.0` and `120.0` seconds. Values `<= 0` fail fast during config loading.
2. `retry_cooldown_seconds`: Must be between `0.5` and `10.0` seconds.
3. `detector_url` & `humanize_url`: Must be valid absolute HTTP/HTTPS URLs.
4. Parsing failures must emit typed `ConfigurationError` and halt startup before agents initialize.
