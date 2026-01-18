/**
 * Dynamic district filtering based on selected region
 * Used in Django Admin for School model
 */
(function() {
    'use strict';

    function initDistrictFilter() {
        const regionSelect = document.getElementById('id_location_region');
        const districtSelect = document.getElementById('id_location_district');

        if (!regionSelect || !districtSelect) {
            return;
        }

        // Store original district value for edit forms
        const originalDistrictId = districtSelect.value;

        // Store all districts for reference
        let allDistricts = [];
        Array.from(districtSelect.options).forEach(option => {
            if (option.value) {
                allDistricts.push({
                    id: option.value,
                    name: option.text,
                    regionId: option.dataset.regionId || null
                });
            }
        });

        function filterDistricts(regionId) {
            // Clear current options (keep empty option)
            districtSelect.innerHTML = '<option value="">---------</option>';

            if (!regionId) {
                return;
            }

            // Fetch districts for selected region
            const url = `/admin/schools/school/get-districts/${regionId}/`;

            fetch(url)
                .then(response => response.json())
                .then(districts => {
                    districts.forEach(district => {
                        const option = document.createElement('option');
                        option.value = district.id;
                        option.textContent = district.name;

                        // Re-select original district if it matches
                        if (district.id.toString() === originalDistrictId) {
                            option.selected = true;
                        }

                        districtSelect.appendChild(option);
                    });
                })
                .catch(error => {
                    console.error('Error fetching districts:', error);
                });
        }

        // Initial filter on page load
        if (regionSelect.value) {
            filterDistricts(regionSelect.value);
        }

        // Filter on region change
        regionSelect.addEventListener('change', function() {
            filterDistricts(this.value);
        });
    }

    // Initialize when DOM is ready
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', initDistrictFilter);
    } else {
        initDistrictFilter();
    }
})();
