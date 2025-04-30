document.addEventListener('DOMContentLoaded', () => {
    const themeSelect = document.getElementById('themeSelect');
    const body = document.body;
    
    // Initialize with saved theme or default to light
    const savedTheme = localStorage.getItem('appTheme') || 'light';
    body.setAttribute('data-theme', savedTheme);
    themeSelect.value = savedTheme;

    // Handle theme changes
    themeSelect.addEventListener('change', (e) => {
        const selectedTheme = e.target.value;
        body.setAttribute('data-theme', selectedTheme);
        localStorage.setItem('appTheme', selectedTheme);
    });
});