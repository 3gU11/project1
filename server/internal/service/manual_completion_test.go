package service

import "testing"

func TestManualCompletionIsolation(t *testing.T) {
	active := []string{"first", "middle", "last"}
	if _, _, err := manualCompletionTarget(active, ""); err == nil {
		t.Fatal("ambiguous whole-line completion accepted")
	}
	if _, _, err := manualCompletionTarget(active, "other-line"); err == nil {
		t.Fatal("foreign batch accepted")
	}
	target, remaining, err := manualCompletionTarget(active, "middle")
	if err != nil || target != "middle" || len(remaining) != 2 || remaining[0] != "first" || remaining[1] != "last" {
		t.Fatalf("wrong scope: %s %v %v", target, remaining, err)
	}
	current := "first"
	status, next := lineStateAfterBatchCompletion(&current, target, remaining)
	if status != "Busy" || next == nil || *next != "first" {
		t.Fatal("unrelated current batch changed")
	}
	current = "middle"
	status, next = lineStateAfterBatchCompletion(&current, target, remaining)
	if status != "Busy" || next == nil || *next != "first" {
		t.Fatal("remaining batch not promoted")
	}
	target, remaining, err = manualCompletionTarget([]string{"last"}, "")
	if err != nil {
		t.Fatal(err)
	}
	status, next = lineStateAfterBatchCompletion(nil, target, remaining)
	if status != "Idle" || next != nil {
		t.Fatal("last batch did not release line")
	}
}
