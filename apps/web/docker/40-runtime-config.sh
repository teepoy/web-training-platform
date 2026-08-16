#!/bin/sh
set -eu

validate_console_url() {
  variable_name="$1"
  value="$2"

  [ -z "$value" ] && return 0

  case "$value" in
    https://*) ;;
    *)
      echo "$variable_name must be an HTTPS URL" >&2
      exit 1
      ;;
  esac

  case "$value" in
    *[!A-Za-z0-9:/?\&=._~%+#@-]*)
      echo "$variable_name contains unsupported URL characters" >&2
      exit 1
      ;;
  esac
}

prefect_url="${OPERATOR_PREFECT_UI_URL:-}"
minio_url="${OPERATOR_MINIO_CONSOLE_URL:-}"
runtime_config_path="${RUNTIME_CONFIG_PATH:-/usr/share/nginx/html/runtime-config.js}"

validate_console_url OPERATOR_PREFECT_UI_URL "$prefect_url"
validate_console_url OPERATOR_MINIO_CONSOLE_URL "$minio_url"

umask 022
{
  printf '%s\n' 'window.__PLATFORM_RUNTIME_CONFIG__ = Object.freeze({'
  printf '  operatorPrefectUiUrl: "%s",\n' "$prefect_url"
  printf '  operatorMinioConsoleUrl: "%s",\n' "$minio_url"
  printf '%s\n' '});'
} > "$runtime_config_path"
