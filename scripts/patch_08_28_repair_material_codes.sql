-- Convert only the legacy synthetic V8-SN-* values after proving that the
-- proposed prefix-suffix codes do not collide among active bindings.
UPDATE machine_component_bindings binding
SET binding.material_code = CONCAT(TRIM(binding.position_code), '-', TRIM(binding.component_serial_no)),
    binding.updated_at = CURRENT_TIMESTAMP
WHERE binding.active = 1
  AND binding.position_code LIKE 'SN-%'
  AND binding.component_serial_no IS NOT NULL
  AND TRIM(binding.component_serial_no) <> ''
  AND binding.material_code = CONCAT('V8-', binding.position_code)
  AND NOT EXISTS (
      SELECT 1
      FROM (
          SELECT CONCAT(TRIM(position_code), '-', TRIM(component_serial_no)) AS proposed_code
          FROM machine_component_bindings
          WHERE active = 1
            AND position_code LIKE 'SN-%'
            AND component_serial_no IS NOT NULL
            AND TRIM(component_serial_no) <> ''
          GROUP BY CONCAT(TRIM(position_code), '-', TRIM(component_serial_no))
          HAVING COUNT(*) > 1
      ) duplicate_codes
  );
