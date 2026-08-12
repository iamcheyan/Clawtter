/**
 * Theme Toggle Script
 * 用于切换明暗主题
 */

(function () {
    'use strict';

    // 主题常量
    const THEME_LIGHT = 'light';
    const THEME_DARK = 'dark';
    const STORAGE_KEY = 'theme';
    const TRANSITION_DURATION = 500; // ms

    // 获取主题切换按钮和图标
    const themeToggle = document.getElementById('themeToggle');
    const themeIcon = themeToggle?.querySelector('.theme-icon');

    // 获取当前主题
    function getTheme() {
        // 优先从 localStorage 读取
        const savedTheme = localStorage.getItem(STORAGE_KEY);
        if (savedTheme === THEME_LIGHT || savedTheme === THEME_DARK) {
            return savedTheme;
        }
        // 其次检查系统偏好
        if (window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches) {
            return THEME_DARK;
        }
        // 默认为深色
        return THEME_DARK;
    }

    // 设置主题
    function setTheme(theme) {
        if (theme === THEME_LIGHT) {
            document.documentElement.setAttribute('data-theme', 'light');
            document.body.setAttribute('data-theme', 'light');
        } else {
            document.documentElement.removeAttribute('data-theme');
            document.body.removeAttribute('data-theme');
        }
        localStorage.setItem(STORAGE_KEY, theme);

        // 更新图标
        if (themeIcon) {
            themeIcon.textContent = theme === THEME_DARK ? '☀️' : '🌙';
        }
    }

    // 切换主题
    function toggleTheme() {
        const currentTheme = getTheme();
        const newTheme = currentTheme === THEME_DARK ? THEME_LIGHT : THEME_DARK;

        // 添加过渡效果
        document.documentElement.style.transition = `background-color ${TRANSITION_DURATION}ms, color ${TRANSITION_DURATION}ms`;
        document.body.style.transition = `background-color ${TRANSITION_DURATION}ms, color ${TRANSITION_DURATION}ms`;

        setTheme(newTheme);

        // 移除过渡效果（避免影响后续样式变化）
        setTimeout(() => {
            document.documentElement.style.transition = '';
            document.body.style.transition = '';
        }, TRANSITION_DURATION);
    }

    // 初始化
    function init() {
        if (!themeToggle) {
            console.warn('Theme toggle button not found');
            return;
        }

        // 设置初始主题
        const theme = getTheme();
        setTheme(theme);

        // 绑定点击事件
        themeToggle.addEventListener('click', toggleTheme);

        // 监听系统主题变化
        if (window.matchMedia) {
            const mediaQuery = window.matchMedia('(prefers-color-scheme: dark)');
            mediaQuery.addEventListener('change', (e) => {
                // 只有当用户没有手动设置过主题时，才跟随系统
                if (!localStorage.getItem(STORAGE_KEY)) {
                    setTheme(e.matches ? THEME_DARK : THEME_LIGHT);
                }
            });
        }
    }

    // DOM 加载完成后初始化
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }
})();
