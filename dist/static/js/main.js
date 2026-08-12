document.addEventListener('DOMContentLoaded', () => {
    // --- Local Dev Delete Button ---
    const isLocal = ['localhost', '127.0.0.1'].includes(window.location.hostname);
    if (isLocal) {
        document.body.classList.add('local-dev');

        const modal = document.getElementById('deleteModal');
        const modalFile = document.getElementById('deleteModalFile');
        const cancelBtn = document.getElementById('deleteCancelBtn');
        const confirmBtn = document.getElementById('deleteConfirmBtn');
        let pendingFile = '';

        function openDeleteModal(file) {
            pendingFile = file;
            if (modalFile) modalFile.textContent = file ? `File: ${file}` : '';
            if (modal) {
                modal.classList.add('visible');
                modal.setAttribute('aria-hidden', 'false');
                document.body.style.overflow = 'hidden';
            }
        }

        function closeDeleteModal() {
            pendingFile = '';
            if (modal) {
                modal.classList.remove('visible');
                modal.setAttribute('aria-hidden', 'true');
                document.body.style.overflow = '';
            }
        }

        async function confirmDelete() {
            const file = pendingFile;
            if (!file) return;

            try {
                const res = await fetch('/__delete', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ file })
                });

                if (!res.ok) {
                    const text = await res.text();
                    alert(`Delete failed: ${text}`);
                    closeDeleteModal();
                    return;
                }

                window.location.reload();
            } catch (err) {
                alert(`Delete failed: ${err}`);
                closeDeleteModal();
            }
        }

        document.querySelectorAll('.tweet-delete-btn').forEach(btn => {
            btn.addEventListener('click', (e) => {
                e.stopPropagation();
                const file = btn.getAttribute('data-file');
                if (!file) return;
                openDeleteModal(file);
            });
        });

        if (cancelBtn) cancelBtn.addEventListener('click', closeDeleteModal);
        if (confirmBtn) confirmBtn.addEventListener('click', confirmDelete);

        if (modal) {
            modal.addEventListener('click', (e) => {
                if (e.target === modal) closeDeleteModal();
            });
        }

        document.addEventListener('keydown', (e) => {
            if (!modal || !modal.classList.contains('visible')) return;
            if (e.key === 'Escape') closeDeleteModal();
        });
    }

    // --- Modal Logic ---
    const themesToggle = document.getElementById('themesToggle');
    const tagsToggle = document.getElementById('tagsToggle');
    const archiveToggle = document.getElementById('archiveToggle');
    const modelStatusToggle = document.getElementById('modelStatusToggle');

    const themesModal = document.getElementById('themesModal');
    const tagsModal = document.getElementById('tagsModal');
    const archiveModal = document.getElementById('archiveModal');
    const modelStatusModal = document.getElementById('modelStatusModal');

    const closeBtns = document.querySelectorAll('.close-modal');

    function openModal(modal) {
        if (!modal) return;
        modal.classList.add('visible');
        document.body.style.overflow = 'hidden';
    }

    function closeModal() {
        document.querySelectorAll('.modal').forEach(m => m.classList.remove('visible'));
        document.body.style.overflow = '';
    }

    if (themesToggle) themesToggle.addEventListener('click', () => openModal(themesModal));
    if (tagsToggle) tagsToggle.addEventListener('click', () => openModal(tagsModal));
    if (archiveToggle) archiveToggle.addEventListener('click', () => openModal(archiveModal));
    if (modelStatusToggle) modelStatusToggle.addEventListener('click', () => {
        openModal(modelStatusModal);
        loadModelStatus();
    });

    closeBtns.forEach(btn => btn.addEventListener('click', closeModal));
    window.addEventListener('click', (e) => {
        if (e.target.classList.contains('modal')) closeModal();
    });

    // --- Model Status ---
    const modelStatusIndicator = document.getElementById('modelStatusIndicator');
    const modelStatusMeta = document.getElementById('modelStatusMeta');
    const modelStatusTable = document.getElementById('modelStatusTable');

    async function loadModelStatus() {
        if (!modelStatusMeta || !modelStatusTable) return;
        modelStatusMeta.textContent = 'Loading...';
        try {
            // Detect if we're on a date page (in /date/ subdirectory)
            const isDatePage = window.location.pathname.includes('/date/');
            const jsonPath = isDatePage ? '../model-status.json' : 'model-status.json';
            const res = await fetch(jsonPath, { cache: 'no-store' });
            if (!res.ok) throw new Error(`HTTP ${res.status}`);
            const data = await res.json();
            const summary = data.summary || {};
            modelStatusMeta.textContent = `Last updated: ${data.generated_at || 'unknown'} | Total: ${summary.total || 0} | Passed: ${summary.passed || 0} | Failed: ${summary.failed || 0}`;

            const rows = (data.results || []).map(r => {
                const badgeClass = r.success ? 'ok' : 'fail';
                const badgeText = r.success ? 'OK' : 'FAIL';
                return `
                    <tr>
                        <td>${r.provider}</td>
                        <td>${r.model}</td>
                        <td><span class="model-status-badge ${badgeClass}">${badgeText}</span></td>
                        <td>${r.status}</td>
                        <td>${r.response || ''}</td>
                    </tr>
                `;
            }).join('');

            modelStatusTable.innerHTML = `
                <table>
                    <thead>
                        <tr>
                            <th>Provider</th>
                            <th>Model</th>
                            <th>Status</th>
                            <th>Detail</th>
                            <th>Response</th>
                        </tr>
                    </thead>
                    <tbody>
                        ${rows || '<tr><td colspan="5">No data</td></tr>'}
                    </tbody>
                </table>
            `;

            updateModelIndicator(summary);
        } catch (err) {
            modelStatusMeta.textContent = `Failed to load model status: ${err.message}`;
            if (modelStatusTable) modelStatusTable.innerHTML = '';
            updateModelIndicator({ failed: 1, total: 1, passed: 0 });
        }
    }

    function updateModelIndicator(summary) {
        if (!modelStatusIndicator) return;
        const total = summary.total || 0;
        const failed = summary.failed || 0;
        modelStatusIndicator.classList.remove('ok', 'warn', 'fail');
        if (total === 0) {
            modelStatusIndicator.classList.add('warn');
        } else if (failed === 0) {
            modelStatusIndicator.classList.add('ok');
        } else if (failed < total) {
            modelStatusIndicator.classList.add('warn');
        } else {
            modelStatusIndicator.classList.add('fail');
        }
    }

    // Prefetch status for indicator on load
    (async () => {
        try {
            const res = await fetch('model-status.json', { cache: 'no-store' });
            if (!res.ok) return;
            const data = await res.json();
            updateModelIndicator(data.summary || {});
        } catch (_) {
            updateModelIndicator({ failed: 1, total: 1, passed: 0 });
        }
    })();

    // --- Filtering Logic (Tags, Search, Archive) ---
    const filterStatus = document.getElementById('filterStatus');
    const currentTagSpan = document.getElementById('currentTag');
    const clearFilterBtn = document.getElementById('clearFilter');
    const tweets = document.querySelectorAll('.tweet');
    const tags = document.querySelectorAll('.tag');

    const searchInput = document.getElementById('searchInput');

    function filterByTag(tagName) {
        const targetTag = tagName.toLowerCase();
        let count = 0;
        tweets.forEach(tweet => {
            const tweetTags = (tweet.getAttribute('data-tags') || "").split(',');
            if (tweetTags.includes(targetTag)) {
                tweet.style.display = 'block';
                count++;
            } else {
                tweet.style.display = 'none';
            }
        });
        updateFilterUI(`#${tagName} (${count})`);
    }

    function filterByTheme(themeName, tagsList) {
        const targetTags = tagsList.split(',').map(t => t.trim().toLowerCase());
        let count = 0;
        tweets.forEach(tweet => {
            const tweetTags = (tweet.getAttribute('data-tags') || "").toLowerCase().split(',');
            const hasMatch = targetTags.some(t => tweetTags.includes(t));
            if (hasMatch) {
                tweet.style.display = 'block';
                count++;
            } else {
                tweet.style.display = 'none';
            }
        });
        updateFilterUI(`Theme: ${themeName} (${count})`);
    }

    function filterByArchive(datePrefix) {
        let count = 0;
        tweets.forEach(tweet => {
            const tweetTime = tweet.querySelector('.tweet-time').textContent;
            if (tweetTime.includes(datePrefix)) {
                tweet.style.display = 'block';
                count++;
            } else {
                tweet.style.display = 'none';
            }
        });
        updateFilterUI(`${datePrefix} (${count} posts)`);
    }

    function filterByDay(dayStr) {
        let count = 0;
        tweets.forEach(tweet => {
            const tweetTime = tweet.querySelector('.tweet-time').textContent;
            if (tweetTime.includes(dayStr)) {
                tweet.style.display = 'block';
                count++;
            } else {
                tweet.style.display = 'none';
            }
        });
        updateFilterUI(`${dayStr} (${count} posts)`);
    }

    function filterBySearch(term) {
        let count = 0;
        tweets.forEach(tweet => {
            const content = tweet.innerText.toLowerCase();
            if (content.includes(term)) {
                tweet.style.display = 'block';
                count++;
            } else {
                tweet.style.display = 'none';
            }
        });
        updateFilterUI(`Search: "${term}" (${count})`);
    }

    function updateFilterUI(statusText) {
        if (filterStatus) filterStatus.classList.add('visible');
        if (currentTagSpan) currentTagSpan.textContent = statusText;
        window.scrollTo({ top: 0, behavior: 'smooth' });
    }

    function clearFilter() {
        tweets.forEach(tweet => tweet.style.display = 'block');
        if (filterStatus) filterStatus.classList.remove('visible');
        if (searchInput) searchInput.value = '';
        tags.forEach(t => t.classList.remove('active'));
        document.querySelectorAll('.theme-card').forEach(c => c.classList.remove('active'));
    }

    // --- Event Listeners ---
    // Themes
    const themeCards = document.querySelectorAll('.theme-card');
    themeCards.forEach(card => {
        card.addEventListener('click', () => {
            const themeName = card.querySelector('.theme-name').textContent;
            const tagsList = card.getAttribute('data-tags');
            filterByTheme(themeName, tagsList);
            closeModal();
            // Highlight active card
            themeCards.forEach(c => c.classList.remove('active'));
            card.classList.add('active');
        });
    });

    // Tags
    tags.forEach(tag => {
        tag.addEventListener('click', (e) => {
            e.stopPropagation();
            const tagName = tag.getAttribute('data-tag');
            filterByTag(tagName);
            closeModal();
            // Highlight active tag
            tags.forEach(t => t.classList.toggle('active', t.getAttribute('data-tag') === tagName));
        });
    });

    // Archive (Calendar)
    const archiveDays = window.__archiveDays || {};
    const calendarGrid = document.getElementById('calendarGrid');
    const calendarTitle = document.getElementById('calendarTitle');
    const calendarMonthFilter = document.getElementById('calendarMonthFilter');
    let currentMonthKey = '';
    let selectedDay = '';

    function getLatestMonthKey() {
        const keys = Object.keys(archiveDays).sort();
        return keys.length ? keys[keys.length - 1] : '';
    }

    function renderCalendar(monthKey) {
        if (!calendarGrid) return;
        if (!monthKey) {
            calendarGrid.innerHTML = '<div class="calendar-empty">No data</div>';
            return;
        }

        currentMonthKey = monthKey;
        const [yearStr, monthStr] = monthKey.split('-');
        const year = Number(yearStr);
        const month = Number(monthStr);

        if (calendarTitle) calendarTitle.textContent = `${year}-${monthStr}`;

        const firstDay = new Date(year, month - 1, 1).getDay();
        const daysInMonth = new Date(year, month, 0).getDate();
        const daysWithPosts = new Set(archiveDays[monthKey] || []);

        const cells = [];
        for (let i = 0; i < firstDay; i++) {
            cells.push('<div class="calendar-day empty"></div>');
        }
        for (let day = 1; day <= daysInMonth; day++) {
            const dd = String(day).padStart(2, '0');
            const dayStr = `${monthKey}-${dd}`;
            const hasPost = daysWithPosts.has(dayStr);
            const isSelected = dayStr === selectedDay;
            cells.push(
                `<div class="calendar-day ${hasPost ? 'has-post' : 'empty'} ${isSelected ? 'selected' : ''}" data-date="${hasPost ? dayStr : ''}">${day}</div>`
            );
        }
        calendarGrid.innerHTML = cells.join('');
    }

    if (calendarGrid) {
        calendarGrid.addEventListener('click', (e) => {
            const target = e.target.closest('.calendar-day.has-post');
            if (!target) return;
            const dateStr = target.getAttribute('data-date');
            if (!dateStr) return;
            selectedDay = dateStr;
            closeModal();

            // Navigate to the date page instead of filtering on current page
            const isHome = window.location.pathname.endsWith('index.html') || window.location.pathname.endsWith('/');
            const datePageUrl = isHome ? `date/${dateStr}.html` : `${dateStr}.html`;
            window.location.href = datePageUrl;
        });
    }

    if (calendarMonthFilter) {
        calendarMonthFilter.addEventListener('click', () => {
            if (!currentMonthKey) return;
            filterByArchive(currentMonthKey);
            closeModal();
        });
    }

    document.querySelectorAll('.archive-month').forEach(item => {
        item.addEventListener('click', () => {
            const monthKey = item.getAttribute('data-date');
            renderCalendar(monthKey);
        });
    });

    if (archiveToggle) {
        archiveToggle.addEventListener('click', () => {
            const latest = getLatestMonthKey();
            renderCalendar(latest);
        });
    }

    // Search
    if (searchInput) {
        searchInput.addEventListener('input', (e) => {
            const term = e.target.value.toLowerCase().trim();
            if (term.length === 0) {
                clearFilter();
            } else {
                filterBySearch(term);
            }
        });
    }

    // Clear
    if (clearFilterBtn) {
        clearFilterBtn.addEventListener('click', clearFilter);
    }

    // --- Type Filtering ---
    // --- Type Filtering (Dropdown) ---
    const filterTrigger = document.getElementById('filterDropdownTrigger');
    const filterDropdown = document.getElementById('typeFilterDropdown');
    const filterItems = document.querySelectorAll('.dropdown-item');
    const currentFilterIcon = document.getElementById('currentFilterIcon');

    if (filterTrigger && filterDropdown) {
        filterTrigger.addEventListener('click', (e) => {
            e.stopPropagation();
            filterDropdown.classList.toggle('visible');
        });

        filterItems.forEach(item => {
            item.addEventListener('click', (e) => {
                e.stopPropagation();
                const type = item.getAttribute('data-type');

                // Update active state
                filterItems.forEach(i => i.classList.remove('active'));
                item.classList.add('active');

                // Update Icon
                if (type === 'all') currentFilterIcon.textContent = '📑';
                if (type === 'original') currentFilterIcon.textContent = '📝';
                if (type === 'repost') currentFilterIcon.textContent = '🔄';

                // Do Filter
                let count = 0;
                tweets.forEach(tweet => {
                    const tweetType = tweet.getAttribute('data-type'); // original or repost
                    if (type === 'all' || tweetType === type) {
                        tweet.style.display = 'block';
                        count++;
                    } else {
                        tweet.style.display = 'none';
                    }
                });

                // Update UI Status bar
                if (type === 'all') {
                    clearFilter();
                } else {
                    const label = type.charAt(0).toUpperCase() + type.slice(1);
                    updateFilterUI(`${label} (${count})`);
                }

                filterDropdown.classList.remove('visible');
            });
        });

        // Close dropdown when clicking outside
        window.addEventListener('click', () => {
            filterDropdown.classList.remove('visible');
        });
    }

    // --- Back to Top Button ---
    const backToTopBtn = document.getElementById('backToTop');

    if (backToTopBtn) {
        // Show/hide button based on scroll position
        window.addEventListener('scroll', () => {
            if (window.pageYOffset > 300) {
                backToTopBtn.classList.add('visible');
            } else {
                backToTopBtn.classList.remove('visible');
            }
        });

        // Scroll to top when clicked
        backToTopBtn.addEventListener('click', () => {
            window.scrollTo({
                top: 0,
                behavior: 'smooth'
            });
        });
    }

    // --- Post-process Links (Open External Links in New Tab) ---
    function processExternalLinks() {
        const links = document.querySelectorAll('.tweet-text a');
        links.forEach(link => {
            const href = link.getAttribute('href');
            if (href && href.startsWith('http')) {
                link.setAttribute('target', '_blank');
                link.setAttribute('rel', 'noopener noreferrer');
            }
        });
    }

    processExternalLinks();

    // --- Lightbox / Image Gallery Logic ---
    const lightbox = document.getElementById('lightbox');
    const lightboxImg = document.getElementById('lightboxImg');
    const lightboxClose = document.querySelector('.lightbox-close');
    const lightboxPrev = document.getElementById('lightboxPrev');
    const lightboxNext = document.getElementById('lightboxNext');

    let currentGallery = [];
    let currentIndex = 0;

    function openLightbox(src, gallery) {
        currentGallery = gallery;
        currentIndex = gallery.indexOf(src);

        lightboxImg.src = src;
        lightbox.classList.add('visible');
        document.body.style.overflow = 'hidden';

        updateNavButtons();
    }

    function closeLightbox() {
        lightbox.classList.remove('visible');
        document.body.style.overflow = '';
    }

    function updateNavButtons() {
        if (currentGallery.length <= 1) {
            lightboxPrev.style.display = 'none';
            lightboxNext.style.display = 'none';
        } else {
            lightboxPrev.style.display = 'block';
            lightboxNext.style.display = 'block';
        }
    }

    function navigate(direction) {
        currentIndex = (currentIndex + direction + currentGallery.length) % currentGallery.length;
        lightboxImg.src = currentGallery[currentIndex];
    }

    // Initialize all tweet images
    function initGallery() {
        const tweets = document.querySelectorAll('.tweet');

        tweets.forEach(tweet => {
            const images = tweet.querySelectorAll('.tweet-text img');
            const gallerySources = Array.from(images).map(img => img.src);

            images.forEach(img => {
                img.addEventListener('click', (e) => {
                    e.stopPropagation();
                    openLightbox(img.src, gallerySources);
                });
            });
        });
    }

    if (lightbox) {
        lightboxClose.addEventListener('click', closeLightbox);
        lightbox.addEventListener('click', (e) => {
            if (e.target === lightbox || e.target.classList.contains('lightbox-content')) {
                closeLightbox();
            }
        });

        lightboxPrev.addEventListener('click', (e) => {
            e.stopPropagation();
            navigate(-1);
        });

        lightboxNext.addEventListener('click', (e) => {
            e.stopPropagation();
            navigate(1);
        });

        // Keyboard Support
        document.addEventListener('keydown', (e) => {
            if (!lightbox.classList.contains('visible')) return;

            if (e.key === 'Escape') closeLightbox();
            if (e.key === 'ArrowLeft') navigate(-1);
            if (e.key === 'ArrowRight') navigate(1);
        });
    }

    initGallery();

    // --- Pull to Refresh (Mobile) ---
    const isMobile = /iPhone|iPad|iPod|Android/i.test(navigator.userAgent);
    if (isMobile) {
        let touchStartY = 0;
        let touchCurrentY = 0;
        let isPulling = false;
        let pullThreshold = 80;
        let maxPull = 120;
        let container = document.querySelector('.container');
        let refreshSpinner = null;
        let refreshText = null;

        // Create refresh indicator behind the content
        function createPullToRefresh() {
            const ptr = document.createElement('div');
            ptr.id = 'pull-to-refresh';
            ptr.innerHTML = `
                <div class="ptr-spinner">
                    <svg viewBox="0 0 24 24" width="24" height="24">
                        <path fill="currentColor" d="M17.65 6.35C16.2 4.9 14.21 4 12 4c-4.42 0-7.99 3.58-7.99 8s3.57 8 7.99 8c3.73 0 6.84-2.55 7.73-6h-2.08c-.82 2.33-3.04 4-5.65 4-3.31 0-6-2.69-6-6s2.69-6 6-6c1.66 0 3.14.69 4.22 1.78L13 11h7V4l-2.35 2.35z"/>
                    </svg>
                </div>
                <div class="ptr-text">Pull to refresh</div>
            `;
            document.body.insertBefore(ptr, document.body.firstChild);

            refreshSpinner = ptr.querySelector('.ptr-spinner');
            refreshText = ptr.querySelector('.ptr-text');
            return ptr;
        }

        // Add styles
        const style = document.createElement('style');
        style.textContent = `
            #pull-to-refresh {
                position: fixed;
                top: 0;
                left: 0;
                right: 0;
                height: 80px;
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                z-index: 0;
                pointer-events: none;
                opacity: 0;
                transition: opacity 0.2s;
            }
            .ptr-spinner {
                width: 24px;
                height: 24px;
                color: var(--text-secondary, #657786);
                transition: transform 0.2s, opacity 0.2s;
            }
            .ptr-spinner svg {
                width: 100%;
                height: 100%;
            }
            .ptr-text {
                font-size: 13px;
                color: var(--text-secondary, #657786);
                margin-top: 8px;
                transition: opacity 0.2s;
            }
            #pull-to-refresh.ptr-ready .ptr-spinner {
                transform: rotate(180deg);
            }
            #pull-to-refresh.ptr-refreshing .ptr-spinner {
                animation: ptrSpin 1s linear infinite;
            }
            #pull-to-refresh.ptr-refreshing .ptr-text::before {
                content: 'Loading...';
            }
            @keyframes ptrSpin {
                from { transform: rotate(0deg); }
                to { transform: rotate(360deg); }
            }
            .container.ptr-pulling {
                transition: transform 0.1s;
            }
            .container.ptr-reset {
                transition: transform 0.3s ease-out;
            }
        `;
        document.head.appendChild(style);

        const ptr = createPullToRefresh();

        function isAtTop() {
            return window.pageYOffset <= 5;
        }

        function setPullProgress(distance) {
            const progress = Math.min(distance / pullThreshold, 1);
            const dampedDistance = distance * 0.6;

            // Move the container down
            container.style.transform = `translateY(${dampedDistance}px)`;
            container.classList.add('ptr-pulling');
            container.classList.remove('ptr-reset');

            // Show refresh indicator behind
            ptr.style.opacity = progress;
            refreshSpinner.style.transform = `rotate(${distance * 2}deg)`;

            // Update text and state
            if (distance >= pullThreshold) {
                ptr.classList.add('ptr-ready');
                refreshText.textContent = 'Release to refresh';
            } else {
                ptr.classList.remove('ptr-ready');
                refreshText.textContent = 'Pull to refresh';
            }
        }

        function resetPull() {
            container.classList.remove('ptr-pulling');
            container.classList.add('ptr-reset');
            container.style.transform = 'translateY(0)';
            ptr.style.opacity = '0';
            ptr.classList.remove('ptr-ready');

            setTimeout(() => {
                ptr.classList.remove('ptr-refreshing');
                refreshText.textContent = 'Pull to refresh';
            }, 300);
        }

        function triggerRefresh() {
            ptr.classList.add('ptr-refreshing');
            ptr.classList.remove('ptr-ready');
            refreshText.textContent = 'Loading...';

            setTimeout(() => {
                window.location.reload();
            }, 800);
        }

        document.addEventListener('touchstart', (e) => {
            if (!isAtTop()) return;
            touchStartY = e.touches[0].clientY;
            isPulling = true;
        }, { passive: true });

        document.addEventListener('touchmove', (e) => {
            if (!isPulling || !isAtTop()) return;

            touchCurrentY = e.touches[0].clientY;
            const pullDistance = touchCurrentY - touchStartY;

            if (pullDistance > 0) {
                e.preventDefault();
                setPullProgress(pullDistance);
            }
        }, { passive: false });

        document.addEventListener('touchend', () => {
            if (!isPulling) return;
            isPulling = false;

            const pullDistance = touchCurrentY - touchStartY;

            if (pullDistance >= pullThreshold && isAtTop()) {
                // Keep the container pulled down
                container.style.transform = `translateY(${pullThreshold * 0.6}px)`;
                triggerRefresh();
            } else {
                resetPull();
            }
        });
    }
});
