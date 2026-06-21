package handler

import (
	"strconv"
	"strings"
	"time"
)

func normalizeImageType(imageType string) string {
	lower := strings.ToLower(strings.TrimSpace(imageType))
	switch lower {
	case "patch_template", "patchtemplate", "patch_reference", "patchreference", "template", "reference":
		return "Reference"
	case "patch_defective", "patchdefective", "defective":
		return "Defective"
	case "patch_difference", "patchdifference", "difference":
		return "Difference"
	case "review", "review_high_mag":
		return "review"
	default:
		return strings.TrimSpace(imageType)
	}
}

func normalizeInspectionTime(raw string) string {
	if raw == "" {
		return raw
	}
	if strings.Contains(raw, "-") {
		return raw
	}
	ts, err := strconv.ParseInt(raw, 10, 64)
	if err != nil {
		return raw
	}
	if ts > 999_999_999_999 {
		ts = ts / 1000
	}
	return time.Unix(ts, 0).UTC().Format(time.RFC3339)
}
