// Safe Telegram Init
try {
    if (window.Telegram && window.Telegram.WebApp) {
        window.Telegram.WebApp.ready();
        window.Telegram.WebApp.expand();
    }
} catch (e) {
    console.warn('Telegram WebApp not available:', e);
}

// Global Error Handler for Loader
window.onerror = function (msg, url, line, col, error) {
    console.error('Global Error:', msg, error);
    $('#tableLoader').fadeOut(100); // Emergency hide
    return false;
};

// Filter State
let currentStart = null;
let currentEnd = null;
let myCharsOnly = false;


function formatDate(date) {
    let year = date.getFullYear();
    let month = ('0' + (date.getMonth() + 1)).slice(-2);
    let day = ('0' + date.getDate()).slice(-2);
    return `${year}-${month}-${day}`;
}

function getActiveInputs() {
    // Default to KH check
    let startId = 'khStartDate';
    let endId = 'khEndDate';

    // Check active tab via class or localStorage
    const activeTab = $('.header-tab.active').attr('id') || localStorage.getItem('activeTab');

    if (activeTab === 'tab-money' || $('#money-pane').hasClass('show') || $('#money-pane').hasClass('active')) {
        startId = 'moneyStartDate';
        endId = 'moneyEndDate';
    } else if (activeTab === 'tab-history' || $('#history-pane').hasClass('show') || $('#history-pane').hasClass('active')) {
        startId = 'historyStartDate';
        endId = 'historyEndDate';
    }

    return {
        start: document.getElementById(startId),
        end: document.getElementById(endId)
    };
}

function applyPeriodFilter() {
    applyFilter();
}

function setRange(type) {
    const today = new Date();
    let start = new Date();
    let end = new Date();

    if (type === 'today') {
        start = new Date();
        end = new Date();
    }
    else if (type === 'monday') {
        const day = today.getDay();
        const diff = today.getDate() - day + (day === 0 ? -6 : 1);
        start.setDate(diff);
    }
    else if (type === 'prev_week') {
        const day = today.getDay();
        const diff = today.getDate() - day + (day === 0 ? -6 : 1);
        const currentMonday = new Date(today.setDate(diff));
        end.setDate(currentMonday.getDate() - 1);
        start.setDate(end.getDate() - 6);
    }

    const inputs = getActiveInputs();
    if (inputs.start) inputs.start.value = formatDate(start);
    if (inputs.end) inputs.end.value = formatDate(end);

    applyFilter();
}


function toggleMyChars() {
    myCharsOnly = !myCharsOnly;
    // Update all toggle switches
    const switches = document.querySelectorAll('.toggle-switch');
    switches.forEach(sw => {
        if (myCharsOnly) {
            sw.classList.add('checked');
        } else {
            sw.classList.remove('checked');
        }
    });

    // Redraw tables safely
    try {
        if ($.fn.DataTable.isDataTable('#khTable')) $('#khTable').DataTable().draw();
        if ($.fn.DataTable.isDataTable('#moneyTable')) $('#moneyTable').DataTable().draw();
        if ($.fn.DataTable.isDataTable('#historyTable')) $('#historyTable').DataTable().draw();
    } catch (e) { }
}

// Global DataTables Filter
// Global DataTables Filter
$.fn.dataTable.ext.search.push(
    function (settings, data, dataIndex) {
        if (!myCharsOnly) return true;

        if (['khTable', 'moneyTable', 'historyTable'].includes(settings.nTable.id)) {
            // Access the original row node to check for HTML elements
            const row = settings.aoData[dataIndex].nTr;
            if (!row) return false;

            // Check for the "status-dot" class (our new "Me" indicator)
            // It could be in any cell, generally the first one (Player/Name)
            if ($(row).find('.status-dot').length > 0) {
                return true;
            }
            return false;
        }
        return true;
    }
);

function toggleAllClasses(state) {
    $('.class-checkbox').prop('checked', state);
}


function applyFilter() {
    const params = new URLSearchParams(window.location.search);

    // Identify Active Tab & Namespace
    let activeTabId = $('.header-tab.active').attr('id');
    // Fallback check panes
    if (!activeTabId) {
        if ($('#money-pane').hasClass('active') || $('#money-pane').hasClass('show')) activeTabId = 'tab-money';
        else if ($('#history-pane').hasClass('active') || $('#history-pane').hasClass('show')) activeTabId = 'tab-history';
        else activeTabId = 'tab-kh';
    }

    const isMoney = (activeTabId === 'tab-money');
    const isHistory = (activeTabId === 'tab-history');

    let namespace = 'kh';
    if (isMoney) namespace = 'money';
    else if (isHistory) namespace = 'history';

    // CLEANUP: Remove parameters from OTHER namespaces to prevent mixing
    // list of known prefixes
    const allNamespaces = ['kh', 'money', 'history'];
    allNamespaces.forEach(ns => {
        if (ns !== namespace) {
            // Remove all keys starting with this namespace
            const keys = Array.from(params.keys());
            keys.forEach(key => {
                if (key.startsWith(ns + '_')) {
                    params.delete(key);
                }
            });
        }
    });

    // Dates
    let startId = 'khStartDate';
    let endId = 'khEndDate';

    if (isMoney) {
        startId = 'moneyStartDate';
        endId = 'moneyEndDate';
    } else if (isHistory) {
        startId = 'historyStartDate';
        endId = 'historyEndDate';
    }

    const sVal = document.getElementById(startId).value;
    const eVal = document.getElementById(endId).value;

    if (sVal) params.set(`${namespace}_start`, sVal);
    else params.delete(`${namespace}_start`);

    if (eVal) params.set(`${namespace}_end`, eVal);
    else params.delete(`${namespace}_end`);

    // Classes (Scoped)
    let scopeSelector = '#kh-pane';
    if (isMoney) scopeSelector = '#money-pane';
    else if (isHistory) scopeSelector = '#history-pane';

    const $scope = $(scopeSelector);

    // Note: To clear previous classes for this namespace, we must replace them.
    // URLSearchParams.append adds. set replaces (single).
    // To handle multiple values with same key:
    params.delete(`${namespace}_classes`);
    $scope.find('.class-checkbox:checked').each(function () {
        params.append(`${namespace}_classes`, $(this).val());
    });

    // Newcomers (Radio)
    let radioName = 'khNewcomers';
    if (isMoney) radioName = 'moneyNewcomers';

    // History: Event Types (Checkbox)
    if (isHistory) {
        params.delete('history_types');
        $('.event-type-checkbox:checked').each(function () {
            params.append('history_types', $(this).val());
        });
        // Remove newcomers invalid param for history
        params.delete('history_newcomers');
    } else {
        // KH/Money Newcomers Logic
        const ncVal = $(`input[name="${radioName}"]:checked`).val();
        if (ncVal && ncVal !== 'all') {
            params.set(`${namespace}_newcomers`, ncVal);
        } else {
            params.delete(`${namespace}_newcomers`);
        }
    }

    // Grouping (Money Only)
    if (isMoney) {
        const periodSelect = document.getElementById('periodSelect');
        if (periodSelect) {
            const groupPeriod = periodSelect.value;
            const groupCount = document.getElementById('periodCount').value;
            params.set('money_group_period', groupPeriod);
            params.set('money_group_count', groupCount);
        }
    }

    // Save Tab
    if (activeTabId) {
        localStorage.setItem('activeTab', activeTabId);
    }

    try {
        if (window.Telegram && window.Telegram.WebApp && window.Telegram.WebApp.HapticFeedback) {
            window.Telegram.WebApp.HapticFeedback.impactOccurred('light');
        }
    } catch (e) { }

    window.location.search = params.toString();
}

// Highlight Preset Buttons on Load
$(document).ready(function () {
    // highlightActiveBenchmarks() - MOVED to main init block


    // Add active class on click for simple feedback (visual only, actual logic via reload)
    $('.btn-group .btn-deck').click(function () {
        if (!$(this).parent().attr('aria-label')) { // Exclude radio group which uses :checked
            $(this).siblings().removeClass('active-preset');
            $(this).addClass('active-preset');
        }
    });
});

function highlightActiveBenchmarks() {
    const inputs = getActiveInputs();
    if (!inputs.start || !inputs.end) return;

    // Determine active scope for buttons
    let activePaneSelector = '#kh-pane';
    const activeTab = $('.header-tab.active').attr('id') || localStorage.getItem('activeTab');

    if (activeTab === 'tab-money' || $('#money-pane').hasClass('show') || $('#money-pane').hasClass('active')) {
        activePaneSelector = '#money-pane';
    } else if (activeTab === 'tab-history' || $('#history-pane').hasClass('show') || $('#history-pane').hasClass('active')) {
        activePaneSelector = '#history-pane';
    }

    const currentS = inputs.start.value;
    const currentE = inputs.end.value;

    function getRange(type) {
        const today = new Date();
        let start = new Date();
        let end = new Date();

        if (type === 'today') {
            start = new Date();
            end = new Date();
        }
        else if (type === 'monday') { // WEEK
            const day = today.getDay();
            const diff = today.getDate() - day + (day === 0 ? -6 : 1);
            start.setDate(diff);
        }
        else if (type === 'prev_week') {
            const day = today.getDay();
            const diff = today.getDate() - day + (day === 0 ? -6 : 1);
            const currentMonday = new Date(today.setDate(diff));
            end.setDate(currentMonday.getDate() - 1);
            start.setDate(end.getDate() - 6);
        }
        return { s: formatDate(start), e: formatDate(end) };
    }

    const t = getRange('today');
    const w = getRange('monday');
    const p = getRange('prev_week');

    // Scope selection to the active pane only
    const $scope = $(activePaneSelector);

    // Clear active class ONLY in the current scope
    $scope.find('.btn-group .btn-deck').removeClass('active-preset');

    if (currentS === t.s && currentE === t.e) {
        $scope.find('.btn-group .btn-deck:contains("TODAY")').addClass('active-preset');
    } else if (currentS === w.s && currentE === w.e) {
        $scope.find('.btn-group .btn-deck:contains("WEEK")').addClass('active-preset');
    } else if (currentS === p.s && currentE === p.e) {
        $scope.find('.btn-group .btn-deck:contains("PREV")').addClass('active-preset');
    }
}

$(document).ready(function () {
    try {
        // Restore active tab safely
        const activeTabId = localStorage.getItem('activeTab');
        if (activeTabId) {
            // Check if tab exists before clicking
            const tabButton = document.getElementById(activeTabId);
            if (tabButton) {
                // Use Bootstrap API to show tab (more reliable than click)
                const tabTrigger = new bootstrap.Tab(tabButton);
                tabTrigger.show();
            }
        }

        // Highlight benchmarks AFTER restoring the tab so we target the correct scope
        highlightActiveBenchmarks();

        // Update selected count
        let count = $('.class-checkbox:checked').length;
        if (count > 0 && count < $('.class-checkbox').length) {
            $('#selectedCount').text(count);
        }

        // Prevent dropdown close
        $('.dropdown-menu').on('click', function (e) {
            e.stopPropagation();
        });

        $('input[name="newcomersRadio"]').on('change', function () {
            applyFilter();
        });

        // Initialize Tables
        var khTable = $('#khTable').DataTable({
            "language": { "url": "https://cdn.datatables.net/plug-ins/1.13.6/i18n/ru.json" },
            "paging": false, "info": false,
            "dom": 'lrtip',
            //"fixedHeader": true,
            "order": [[10, "asc"]],
            "columnDefs": [
                { "targets": [10], "visible": false, "searchable": true }
            ]
        });

        var moneyTable = $('#moneyTable').DataTable({
            "language": { "url": "https://cdn.datatables.net/plug-ins/1.13.6/i18n/ru.json" },
            "paging": false, "info": false,
            "dom": 'lrtip',
            //"fixedHeader": true,
            "order": [[0, "asc"]],
            "drawCallback": function (settings) {
                applyHeatmap(this.api());
            }
        });

        function applyHeatmap(api) {
            // Iterate over all columns except the first (Name)
            api.columns().every(function (colIdx) {
                if (colIdx === 0) return; // Skip Name column

                const colData = this.data();
                const nodes = this.nodes();

                // 1. Find Max Value in Column
                let maxVal = 0;
                colData.each(function (value) {
                    const num = parseFloat(String(value).replace(/\s/g, '')) || 0;
                    if (num > maxVal) maxVal = num;
                });

                // 2. Apply Styles
                this.nodes().to$().each(function (index) {
                    const cell = $(this);
                    const valStr = String(colData[index]);
                    const val = parseFloat(valStr.replace(/\s/g, '')) || 0;

                    // Clean previous styles on the TD itself
                    cell[0].style.removeProperty('background-color');
                    cell[0].style.removeProperty('color');

                    if (val === 0) {
                        cell.html(val); // Just text
                        cell[0].style.setProperty('color', '#555', 'important');
                    } else {
                        // Chips for values > 0
                        // Opacity Range: 0.15 (low) - 0.4 (high)
                        let ratio = (val / maxVal);

                        // Linear interpolation: 0.15 + (ratio * (0.4 - 0.15))
                        let opacity = 0.15 + (ratio * 0.25);

                        // Create Chip with jQuery
                        const chip = $('<div>', {
                            class: 'heatmap-chip',
                            text: val
                        });

                        // Apply Chip Styles (Background only)
                        chip.css({
                            'background-color': `rgba(217, 0, 34, ${opacity})`,
                            'color': '#fff'
                        });

                        // Completely replace cell content with the chip
                        cell.empty().append(chip);
                    }
                });
            });
        }

        var historyTable = $('#historyTable').DataTable({
            "language": { "url": "https://cdn.datatables.net/plug-ins/1.13.6/i18n/ru.json" },
            "paging": false, "info": false,
            "dom": 'lrtip',
            "ordering": false,
            //"fixedHeader": true
        });

        // Global Search Init (bind to headers)
        // filterTable() is called via onkeyup in HTML


        // Safe Tab Switching
        $('button[data-bs-toggle="tab"]').on('shown.bs.tab', function (e) {
            try {
                localStorage.setItem('activeTab', e.target.id);
                // Safe redraw
                $.fn.dataTable.tables({ visible: true, api: true }).columns.adjust();
                window.dispatchEvent(new Event('resize'));
            } catch (err) {
                console.error('Tab switch warning:', err);
            }
        });

    } catch (criticalError) {
        console.error('Critical Script Error:', criticalError);
    } finally {
        // ALWAYS hide loader
        setTimeout(function () {
            $('#tableLoader').fadeOut(300);
        }, 300);
    }
});

// Edit Player Modal
$(document).on('click', '.edit-player-btn', function (e) {
    try {
        e.preventDefault();
        const roleId = $(this).data('role-id');
        const currentName = $(this).data('name');
        const classIcon = $(this).data('class-icon');

        const currentClassId = (typeof classIconMap !== 'undefined' && classIconMap[classIcon]) || -1;

        $('#editRoleId').val(roleId);
        $('#displayRoleId').val(roleId);
        const nickname = currentName.startsWith('ID ') ? '' : currentName;
        $('#editNickname').val(nickname);
        $('#editClass').val(currentClassId);
        $('#saveStatus').hide();
        new bootstrap.Modal($('#editPlayerModal')[0]).show();
    } catch (e) { console.error('Error opening modal:', e); }
});

async function savePlayerData() {
    const roleId = $('#editRoleId').val();
    const nickname = $('#editNickname').val().trim();
    const classId = parseInt($('#editClass').val());
    const statusDiv = $('#saveStatus');

    statusDiv.show().removeClass().addClass('alert alert-info py-2 small').text('💾 Сохранение...');

    try {
        const nicknameResponse = await fetch('/api/update_nickname', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ role_id: roleId, nickname: nickname })
        });
        const nicknameResult = await nicknameResponse.json();
        if (nicknameResult.status !== 'ok') throw new Error(nicknameResult.message);

        const classResponse = await fetch('/api/update_class', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ role_id: roleId, class_id: classId })
        });
        const classResult = await classResponse.json();
        if (classResult.status !== 'ok') throw new Error(classResult.message);

        statusDiv.removeClass().addClass('alert alert-success py-2 small').text('✅ Данные успешно сохранены!');
        setTimeout(() => window.location.reload(), 1000);

    } catch (error) {
        statusDiv.removeClass().addClass('alert alert-danger py-2 small').text('❌ Ошибка: ' + error.message);
    }
}

async function triggerScraper() {
    if (!confirm('Запустить обновление данных с PWOBS?')) return;
    const btn = document.getElementById('pwobsBtn');
    if (btn) btn.disabled = true;

    try {
        const response = await fetch('/api/scrape_players', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ server: 'capella' })
        });

        // Debug: Check for non-JSON response
        const contentType = response.headers.get("content-type");
        if (contentType && contentType.indexOf("application/json") === -1) {
            const text = await response.text();
            throw new Error(`Ошибка сервера (${response.status}): ${text.substring(0, 150)}...`);
        }

        const result = await response.json();
        if (result.status === 'ok') alert('✅ Обновление запущено! ' + result.message);
        else alert('❌ Ошибка: ' + result.message);
    } catch (error) {
        console.error('Scraper Error:', error);
        alert('❌ Ошибка выполнения: ' + error.message);
    } finally {
        if (btn) btn.disabled = false;
    }
}

async function onTelegramAuth(user) {
    if (!user) return;
    try {
        const response = await fetch('/api/login/widget', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(user)
        });
        const result = await response.json();
        if (result.status === 'ok') window.location.reload();
        else alert('❌ Ошибка авторизации: ' + result.message);
    } catch (error) {
        alert('❌ Ошибка сети: ' + error.message);
    }
}

async function logout() {
    try {
        await fetch('/api/logout', { method: 'POST' });
        window.location.reload();
    } catch (error) {
        console.error('Logout failed:', error);
        window.location.reload();
    }
}

// Spider Scroll Tracker
window.addEventListener('scroll', function () {
    try {
        const docHeight = document.documentElement.scrollHeight - window.innerHeight;
        const scrollTop = window.scrollY;
        let percent = 0;
        if (docHeight > 0) percent = (scrollTop / docHeight) * 100;
        const thumb = document.getElementById('spiderThumb');
        if (thumb) thumb.style.top = Math.min(percent, 96) + '%';
    } catch (e) { }
});

// Safety Timeout to ensure loader hides even if JS crashes wildly
setTimeout(function () {
    if ($('#tableLoader').is(':visible')) {
        console.warn('Emergency loader cleanup');
        $('#tableLoader').fadeOut(300);
    }
}, 3000);

// Global Search Function
window.filterTable = function () {
    var input = document.getElementById("headerSearchInput");
    if (input) {
        var filter = input.value;
        // Search all initialized DataTables
        $.fn.dataTable.tables({ api: true }).search(filter).draw();
    }
};

/* --- Scroll To Top Logic --- */
$(document).ready(function () {
    const scrollBtn = $('#scrollToTopBtn');

    $(window).scroll(function () {
        if ($(this).scrollTop() > 300) {
            scrollBtn.addClass('show');
        } else {
            scrollBtn.removeClass('show');
        }
    });

    scrollBtn.click(function () {
        $('html, body').animate({ scrollTop: 0 }, 500); // Smooth jQuery scroll
        return false;
    });
});
