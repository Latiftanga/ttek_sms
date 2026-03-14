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

            function loadDistricts(regionId, selectDistrictId) {
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

                        // Re-select district if provided
                        if (selectDistrictId) {
                            districtField.val(selectDistrictId);
                        }
                    },
                    error: function() {
                        districtField.empty().append('<option value="">Error loading districts</option>');
                        districtField.prop('disabled', false);
                    }
                });
            }

            // Listen for change on the region field
            // Use 'change' event which works for both native <select> and Select2
            regionField.on('change', function() {
                loadDistricts($(this).val(), null);
            });

            // If region is selected but district is empty on page load, load districts
            if (regionField.val() && !districtField.val()) {
                loadDistricts(regionField.val(), initialDistrictId);
            }
        }
    });
})(django.jQuery);
