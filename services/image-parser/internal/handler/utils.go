package handler

import (
	"fmt"
	"strconv"
	"strings"
	"time"
)

func normalizeImageType(imageType string) string {
	lower := strings.ToLower(strings.TrimSpace(imageType))
	base, imageID, hasImageID := strings.Cut(lower, ":")
	var normalized string
	switch base {
	case "patch_template", "patchtemplate", "patch_reference", "patchreference", "template", "reference":
		normalized = "Reference"
	case "patch_defective", "patchdefective", "defective":
		normalized = "Defective"
	case "patch_difference", "patchdifference", "difference":
		normalized = "Difference"
	case "patch_mask", "patchmask", "mask":
		normalized = "Mask"
	case "review", "review_high_mag":
		return "review"
	default:
		return strings.TrimSpace(imageType)
	}
	if !hasImageID {
		return normalized
	}
	if normalized == "Defective" {
		return strings.TrimSpace(imageType)
	}
	parsed, err := strconv.Atoi(strings.TrimSpace(imageID))
	if err != nil || parsed < 0 {
		return strings.TrimSpace(imageType)
	}
	return fmt.Sprintf("%s:%d", normalized, parsed)
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
