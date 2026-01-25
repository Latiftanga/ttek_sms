// Dynamic enabled_levels based on education_system selection
// Dynamic district filtering based on region selection
(function($) {
    'use strict';

    $(document).ready(function() {
        // ============================================
        // Education System → Enabled Levels filtering
        // ============================================
        const educationSystemField = $('#id_education_system');

        // Define which levels belong to which system
        const basicLevels = ['creche', 'nursery', 'kg', 'basic'];
        const shsLevels = ['shs'];

        function updateEnabledLevels() {
            const selectedSystem = educationSystemField.val();

            // Get all checkbox inputs for enabled_levels
            const checkboxes = $('input[name="enabled_levels"]');

            checkboxes.each(function() {
                const checkbox = $(this);
                const value = checkbox.val();
                const label = checkbox.closest('label').length ? checkbox.closest('label') : checkbox.parent();

                if (selectedSystem === 'basic') {
                    // Basic only - show basic levels, hide SHS
                    if (shsLevels.includes(value)) {
                        label.hide();
                        checkbox.prop('checked', false);
                    } else {
                        label.show();
                    }
                } else if (selectedSystem === 'shs') {
                    // SHS only - show SHS, hide basic levels
                    if (basicLevels.includes(value)) {
                        label.hide();
                        checkbox.prop('checked', false);
                    } else {
                        label.show();
                    }
                } else {
                    // Both - show all
                    label.show();
                }
            });
        }

        // Run on page load
        if (educationSystemField.length) {
            updateEnabledLevels();
            educationSystemField.on('change', updateEnabledLevels);
        }

        // ============================================
        // Region → District dynamic filtering
        // ============================================
        const regionField = $('#id_location_region');
        const districtField = $('#id_location_district');

        if (regionField.length && districtField.length) {
            // Store the initial district value (for edit forms)
            const initialDistrictId = districtField.val();

            function updateDistricts() {
                const regionId = regionField.val();

                if (!regionId) {
                    // No region selected - clear districts
                    districtField.empty().append('<option value="">---------</option>');
                    districtField.prop('disabled', true);
                    return;
                }

                // Show loading state
                districtField.prop('disabled', true);

                // Fetch districts for the selected region
                $.ajax({
                    url: '/admin/schools/school/get-districts/' + regionId + '/',
                    dataType: 'json',
                    success: function(data) {
                        districtField.empty().append('<option value="">---------</option>');
                        $.each(data, function(index, district) {
                            districtField.append(
                                $('<option></option>')
                                    .val(district.id)
                                    .text(district.name)
                            );
                        });
                        districtField.prop('disabled', false);

                        // Re-select initial district if it exists in the new list
                        if (initialDistrictId) {
                            districtField.val(initialDistrictId);
                        }
                    },
                    error: function() {
                        districtField.empty().append('<option value="">Error loading districts</option>');
                        districtField.prop('disabled', false);
                    }
                });
            }

            // Only run on change (not on load, to preserve existing value)
            regionField.on('change', function() {
                // Clear initial value on change so we don't re-select old district
                updateDistricts();
            });

            // If region is selected but district is empty, load districts
            if (regionField.val() && !districtField.val()) {
                updateDistricts();
            }
        }
    });
})(django.jQuery);
