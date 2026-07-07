const root = document.documentElement;
const savedTheme = localStorage.getItem('theme') || 'light';
root.dataset.theme = savedTheme;
const btn = document.getElementById('themeToggle');
if (btn) {
  btn.textContent = savedTheme === 'dark' ? '☀️ الوضع النهاري' : '🌙 الوضع الليلي';
  btn.addEventListener('click', () => {
    const next = root.dataset.theme === 'dark' ? 'light' : 'dark';
    root.dataset.theme = next;
    localStorage.setItem('theme', next);
    btn.textContent = next === 'dark' ? '☀️ الوضع النهاري' : '🌙 الوضع الليلي';
  });
}
if ('serviceWorker' in navigator) {
  window.addEventListener('load', () => navigator.serviceWorker.register('/static/service-worker.js'));
}
