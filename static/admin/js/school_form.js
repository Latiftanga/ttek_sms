// Dynamic enabled_levels based on education_system selection
(function($) {
    'use strict';

    $(document).ready(function() {
        const educationSystemField = $('#id_education_system');
        const enabledLevelsContainer = $('fieldset:has(#id_enabled_levels)').length ?
            $('fieldset:has(#id_enabled_levels)') :
            $('#id_enabled_levels').closest('.form-row, .field-enabled_levels, div');

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

            // Run on change
            educationSystemField.on('change', updateEnabledLevels);
        }
    });
})(django.jQuery);
