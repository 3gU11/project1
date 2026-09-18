package engine

import (
	"fmt"
	"os"
	"strings"
)

func sourceOfFunction(fileName, startMarker, endMarker string) (string, error) {
	content, err := os.ReadFile(fileName)
	if err != nil {
		return "", err
	}
	source := string(content)
	start := strings.Index(source, startMarker)
	if start < 0 {
		return "", fmt.Errorf("start marker not found: %s", startMarker)
	}
	end := strings.Index(source[start:], endMarker)
	if end < 0 {
		return "", fmt.Errorf("end marker not found: %s", endMarker)
	}
	return source[start : start+end], nil
}
