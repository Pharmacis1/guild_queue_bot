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
    // Try to hide loader using vanilla JS if jQuery is dead
    var loader = document.getElementById('tableLoader');
    if (loader) loader.style.display = 'none';
    return false;
};

// DEBUG: Force hide loader to verify script execution
console.log("JS STARTED");

if (typeof $ === 'undefined') {
    console.error("CRITICAL: jQuery is NOT loaded!");
    alert("ОШИБКА: Библиотека jQuery не загрузилась. Возможно проблема с VPN или блокировщиком рекламы. Попробуйте отключить их.");
    // Emergency hide
    var loader = document.getElementById('tableLoader');
    if (loader) loader.style.display = 'none';
} else {
    $('#tableLoader').fadeOut(500);
}

// Filter State
let currentStart = null;
let currentEnd = null;
let myCharsOnly = false;

// Queue Mode Toggle (for add queue form)
function setQueueMode(isAuto) {
    // Support both old class (queue-mode-btn) and new class (queue-mode-option)
    if (isAuto) {
        $('#queueModeAuto').addClass('active');
        $('#queueModeSingle').removeClass('active');
    } else {
        $('#queueModeSingle').addClass('active');
        $('#queueModeAuto').removeClass('active');
    }
}

// Character Status Toggle (Main/Twin)
function setCharStatus(status) {
    if (status === 'alt') {
        $('#btnStatusAlt').addClass('active');
        $('#btnStatusMain').removeClass('active');
        $('#charStatusValue').val('alt');
        $('#statusAlt').prop('checked', true);
    } else {
        $('#btnStatusMain').addClass('active');
        $('#btnStatusAlt').removeClass('active');
        $('#charStatusValue').val('main');
        $('#statusMain').prop('checked', true);
    }
}

// In Clan Toggle
function setInClan(inClan) {
    if (inClan) {
        $('#btnInClanYes').addClass('active');
        $('#btnInClanNo').removeClass('active');
        $('#editInClan').prop('checked', true);
    } else {
        $('#btnInClanNo').addClass('active');
        $('#btnInClanYes').removeClass('active');
        $('#editInClan').prop('checked', false);
    }
    // Update header badge
    const $badge = $('#profileStatusBadge');
    if (!inClan) {
        $badge.removeClass('status-badge-active status-badge-afk').addClass('status-badge-inactive').html('⚫ Вне клана');
    } else {
        $badge.removeClass('status-badge-inactive status-badge-afk').addClass('status-badge-active').html('🟢 В клане');
    }
}

// Update class icon when selection changes
function updateClassIcon() {
    const classId = $('#editClass').val();
    const iconId = (classId >= 0 && classId <= 16) ? classId : 0;
    $('#editClassIcon').attr('src', `/static/icons/${iconId}.png`);
    // Also update hero header icon
    $('#profileClassIcon').attr('src', `/static/icons/${iconId}.png`);
    // Update class text in hero
    const className = $('#editClass option:selected').text() || 'Неизвестно';
    $('#profileClassText').text(className);
}


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
        if ($.fn.DataTable.isDataTable('#historyTable')) $('#historyTable').DataTable().draw(); // Keep this for legacy

        // Filter Timeline (History)
        if (myCharsOnly) {
            $('.history-entry').hide();
            $('.history-entry[data-is-mine="true"]').show();
        } else {
            $('.history-entry').show();
        }
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
        let activeTabId = localStorage.getItem('activeTab');
        if (!activeTabId || !['tab-kh', 'tab-money', 'tab-history'].includes(activeTabId)) {
            activeTabId = 'tab-kh';
        }

        const tabButton = document.getElementById(activeTabId);
        if (tabButton) {
            console.log("Restoring Tab via Click:", activeTabId);
            tabButton.click();
        } else {
            const defBtn = document.getElementById('tab-kh');
            if (defBtn) defBtn.click();
        }

        // Force hide loader (just in case)
        setTimeout(() => $('#tableLoader').fadeOut(300), 500);

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
            "language": {
                "processing": "Подождите...",
                "search": "Поиск:",
                "lengthMenu": "Показать _MENU_ записей",
                "info": "Записи с _START_ до _END_ из _TOTAL_ записей",
                "infoEmpty": "Записи с 0 до 0 из 0 записей",
                "infoFiltered": "(отфильтровано из _MAX_ записей)",
                "loadingRecords": "Загрузка записей...",
                "zeroRecords": "Записи отсутствуют.",
                "emptyTable": "В таблице отсутствуют данные",
                "paginate": {
                    "first": "Первая",
                    "previous": "Предыдущая",
                    "next": "Следующая",
                    "last": "Последняя"
                },
                "aria": {
                    "sortAscending": ": активировать для сортировки столбца по возрастанию",
                    "sortDescending": ": активировать для сортировки столбца по убыванию"
                }
            },
            "paging": false, "info": false,
            "dom": 'lrtip',
            //"fixedHeader": true,
            "order": [[10, "asc"]],
            "columnDefs": [
                { "targets": [10], "visible": false, "searchable": true }
            ]
        });

        var moneyTable = $('#moneyTable').DataTable({
            "language": {
                "processing": "Подождите...",
                "search": "Поиск:",
                "lengthMenu": "Показать _MENU_ записей",
                "info": "Записи с _START_ до _END_ из _TOTAL_ записей",
                "infoEmpty": "Записи с 0 до 0 из 0 записей",
                "infoFiltered": "(отфильтровано из _MAX_ записей)",
                "loadingRecords": "Загрузка записей...",
                "zeroRecords": "Записи отсутствуют.",
                "emptyTable": "В таблице отсутствуют данные",
                "paginate": {
                    "first": "Первая",
                    "previous": "Предыдущая",
                    "next": "Следующая",
                    "last": "Последняя"
                },
                "aria": {
                    "sortAscending": ": активировать для сортировки столбца по возрастанию",
                    "sortDescending": ": активировать для сортировки столбца по убыванию"
                }
            },
            "paging": false, "info": false,
            "dom": 'lrtip',
            //"fixedHeader": true,
            "order": [[0, "asc"]],
            "drawCallback": function (settings) {
                applyHeatmap(this.api());
                initTopScroll();
            }
        });

        function initTopScroll() {
            const tableWrapper = $('#moneyTableWrapper');
            const topScroll = $('#moneyTopScroll');
            const topScrollInner = topScroll.find('.top-scrollbar-inner');
            const table = $('#moneyTable');

            // 1. Check if scroll is needed
            const scrollWidth = tableWrapper[0].scrollWidth;
            const clientWidth = tableWrapper[0].clientWidth;

            if (scrollWidth > clientWidth) {
                topScroll.show();
                topScrollInner.width(scrollWidth);

                // Sync Scroll
                topScroll.off('scroll').on('scroll', function () {
                    tableWrapper.scrollLeft($(this).scrollLeft());
                });

                tableWrapper.off('scroll').on('scroll', function () {
                    topScroll.scrollLeft($(this).scrollLeft());
                });
            } else {
                topScroll.hide();
            }
        }

        $(window).resize(function () {
            initTopScroll();
        });

        function applyHeatmap(api) {
            // Iterate over all columns except the first (Name)
            api.columns().every(function (colIdx) {
                if (colIdx === 0) return; // Skip Name column

                const colData = this.data();
                const nodes = this.nodes();

                // 1. Find Max Value in Column (extract text from HTML if needed)
                let maxVal = 0;
                colData.each(function (value) {
                    // Strip HTML tags and extract text content
                    const textContent = $('<div>').html(String(value)).text().trim();
                    const num = parseFloat(textContent.replace(/\s/g, '')) || 0;
                    if (num > maxVal) maxVal = num;
                });
                // Guard against division by zero
                if (maxVal === 0) maxVal = 1;

                // 2. Apply Styles
                this.nodes().to$().each(function (index) {
                    const cell = $(this);

                    // Skip pre-join dash cells (opacity 0.3 dash)
                    if (cell.find('span[style*="opacity"]').length > 0 && cell.text().trim() === '—') {
                        return; // Preserve pre-join indicator
                    }

                    // Read chip type from data attribute
                    const chipSpan = cell.find('span[data-chip-type]');
                    const chipType = chipSpan.length > 0 ? chipSpan.data('chip-type') : 'normal';

                    // FIXED: Extract text content from cell DOM
                    const valStr = cell.text().trim();
                    const val = parseFloat(valStr.replace(/\s/g, '')) || 0;

                    // Clean previous styles on the TD itself
                    cell[0].style.removeProperty('background-color');
                    cell[0].style.removeProperty('color');

                    // For normal cells: zeros are plain text, values get red heatmap
                    // For newcomer/AFK cells: ALL values get colored chips (including zeros)

                    if (chipType === 'normal' && val === 0) {
                        // Normal zeros: plain text
                        cell.html(val);
                        cell[0].style.setProperty('color', '#555', 'important');
                    } else {
                        // Create Chip for: all non-zeros, AND all newcomer/AFK cells (including zeros)
                        const chip = $('<div>', {
                            class: 'heatmap-chip',
                            text: val
                        });

                        if (chipType === 'newcomer') {
                            // Dark turquoise for newcomers (all values including 0)
                            chip.css({
                                'background-color': 'rgba(0, 128, 128, 0.5)',
                                'color': '#e0ffff',
                                'border': '1px solid rgba(0, 200, 200, 0.4)'
                            });
                        } else if (chipType === 'afk') {
                            // Amber/Yellow for AFK (all values including 0)
                            chip.css({
                                'background-color': 'rgba(212, 175, 55, 0.4)',
                                'color': '#fff8dc',
                                'border': '1px solid rgba(212, 175, 55, 0.5)'
                            });
                        } else {
                            // Normal: Red heatmap gradient (only for values > 0)
                            let ratio = (val / maxVal);
                            let opacity = 0.15 + (ratio * 0.25);
                            chip.css({
                                'background-color': `rgba(217, 0, 34, ${opacity})`,
                                'color': '#fff'
                            });
                        }

                        // Replace cell content with the chip
                        cell.empty().append(chip);
                    }
                });
            });
        }

        var historyTable = $('#historyTable').DataTable({
            "language": {
                "processing": "Подождите...",
                "search": "Поиск:",
                "lengthMenu": "Показать _MENU_ записей",
                "info": "Записи с _START_ до _END_ из _TOTAL_ записей",
                "infoEmpty": "Записи с 0 до 0 из 0 записей",
                "infoFiltered": "(отфильтровано из _MAX_ записей)",
                "loadingRecords": "Загрузка записей...",
                "zeroRecords": "Записи отсутствуют.",
                "emptyTable": "В таблице отсутствуют данные",
                "paginate": {
                    "first": "Первая",
                    "previous": "Предыдущая",
                    "next": "Следующая",
                    "last": "Последняя"
                },
                "aria": {
                    "sortAscending": ": активировать для сортировки столбца по возрастанию",
                    "sortDescending": ": активировать для сортировки столбца по убыванию"
                }
            },
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
        e.stopPropagation();

        const roleId = $(this).data('role-id');
        const currentName = $(this).data('name');

        // Reset Fields
        $('#editRoleId').val(roleId);
        $('#displayRoleId').text(roleId);
        $('#editNickname').val('Загрузка...');
        $('#editTgId').val('');
        $('#userLinkStatus').text('Проверка...');

        // Reset AFK Dates
        $('#editAfkStart').val('');
        $('#editAfkEnd').val('');
        $('#afkHistoryList').html('<li>Загрузка...</li>');
        $('#afkDetails').hide();

        $('#statusMain').prop('checked', true);

        $('#linkedCharsList').html('<li class="list-group-item bg-transparent text-muted text-center py-2"><div class="spinner-border spinner-border-sm"></div></li>');
        $('#activeQueuesList').html('<li class="list-group-item bg-transparent text-muted text-center py-2"><div class="spinner-border spinner-border-sm"></div></li>');

        $('#saveStatus').hide();
        new bootstrap.Modal($('#editPlayerModal')[0]).show();

        // Fetch Full Data
        fetch('/api/get_player', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ role_id: roleId })
        })
            .then(r => r.json())
            .then(data => {
                if (data.status === 'ok') {
                    const p = data.player;
                    $('#editNickname').val(p.nickname || '');
                    $('#editClass').val(p.class_id);
                    $('#editInClan').prop('checked', p.in_clan);

                    // Profile Hero Header
                    $('#profileHeroName').text(p.nickname || 'Неизвестный');
                    const className = $('#editClass option:selected').text() || 'Неизвестно';
                    // Set class icon image based on class_id
                    const iconId = (p.class_id >= 0 && p.class_id <= 16) ? p.class_id : 0;
                    $('#profileClassIcon').attr('src', `/static/icons/${iconId}.png`);
                    $('#editClassIcon').attr('src', `/static/icons/${iconId}.png`);
                    $('#profileClassText').text(className);

                    // Status Badge
                    const $badge = $('#profileStatusBadge');
                    if (!p.in_clan) {
                        $badge.removeClass('status-badge-active status-badge-afk').addClass('status-badge-inactive').html('⚫ Вне клана');
                    } else if (p.user && p.user.is_afk) {
                        $badge.removeClass('status-badge-active status-badge-inactive').addClass('status-badge-afk').html('🟡 AFK');
                    } else {
                        $badge.removeClass('status-badge-inactive status-badge-afk').addClass('status-badge-active').html('🟢 В клане');
                    }

                    // Status
                    if (p.is_alt) {
                        $('#statusAlt').prop('checked', true);
                        setCharStatus('alt');
                    } else {
                        $('#statusMain').prop('checked', true);
                        setCharStatus('main');
                    }

                    // Sync in clan toggle
                    if (p.in_clan) {
                        $('#btnInClanYes').addClass('active');
                        $('#btnInClanNo').removeClass('active');
                    } else {
                        $('#btnInClanNo').addClass('active');
                        $('#btnInClanYes').removeClass('active');
                    }

                    // User Link
                    if (p.user) {
                        $('#editTgId').val(p.user.telegram_id || '');
                        $('#userLinkStatus').removeClass('bg-secondary bg-danger').addClass('bg-success').text('Привязан');
                        if (p.user.username) {
                            $('#tgProfileLink').attr('href', `https://t.me/${p.user.username}`);
                        } else {
                            $('#tgProfileLink').attr('href', '#');
                        }

                        // AFK Dates
                        // Assuming string "YYYY-MM-DD HH:MM:SS" or similar. Input[type=date] needs YYYY-MM-DD
                        if (p.user.afk_start) $('#editAfkStart').val(p.user.afk_start.split(' ')[0]);
                        if (p.user.afk_end) $('#editAfkEnd').val(p.user.afk_end.split(' ')[0]);

                    } else {
                        $('#editTgId').val('');
                        $('#userLinkStatus').removeClass('bg-success bg-danger').addClass('bg-secondary').text('Не привязан');
                        $('#tgProfileLink').attr('href', '#');
                    }

                    // AFK History
                    const histList = $('#afkHistoryList');
                    histList.empty();
                    if (p.afk_history && p.afk_history.length > 0) {
                        p.afk_history.forEach(h => {
                            let s = h.start ? h.start.split(' ')[0] : '?';
                            let e = h.end ? h.end.split(' ')[0] : '?';
                            histList.append(`
                            <li class="d-flex justify-content-between align-items-center mb-1">
                                <span>• ${s} — ${e}</span>
                                <button class="btn btn-sm btn-link text-danger p-0" onclick="deleteObj('afk', ${h.id}, ${roleId})">✖</button>
                            </li>
                        `);
                        });
                    } else {
                        histList.append('<li>Нет истории</li>');
                    }

                    // Other Chars - Card Style
                    const charsList = $('#linkedCharsList');
                    const charsCards = $('#linkedCharsCards');
                    charsList.empty();
                    charsCards.empty();
                    if (p.other_chars && p.other_chars.length > 0) {
                        p.other_chars.forEach(c => {
                            const iconId = (c.class_id >= 0 && c.class_id <= 16) ? c.class_id : 0;
                            charsCards.append(`
                            <div class="char-card">
                                <button class="char-card-delete" onclick="deleteObj('char', '${c.nickname}', ${roleId})">✖</button>
                                <img class="char-card-icon" src="/static/icons/${iconId}.png" style="width: 32px; height: 32px;">
                                <span class="char-card-name">${c.nickname || 'ID ' + c.role_id}</span>
                                <span class="char-card-type">${c.is_alt ? '👤 Твин' : '⭐ Основа'}</span>
                            </div>
                        `);
                        });
                    } else {
                        charsCards.append('<div class="profile-empty-state"><div class="profile-empty-state-icon">👥</div>Нет привязанных персонажей</div>');
                    }

                    // Queues - Badge Style
                    const queuesList = $('#activeQueuesList');
                    const queuesCards = $('#activeQueuesCards');
                    queuesList.empty();
                    queuesCards.empty();
                    if (p.queues && p.queues.length > 0) {
                        p.queues.forEach(q => {
                            let icon = q.is_auto ? '🔄' : '🗓️';
                            let charBadge = q.signed_char ? `<span class="queue-badge-char">${q.signed_char}</span>` : '';

                            queuesCards.append(`
                            <div class="queue-badge">
                                <span class="queue-badge-mode">${icon}</span>
                                <span class="queue-badge-name">${q.queue_name}</span>
                                ${charBadge}
                                <button class="queue-badge-delete" onclick="deleteObj('queue', ${q.entry_id}, ${roleId})">✖</button>
                            </div>
                        `);
                        });
                    } else {
                        queuesCards.append('<div class="profile-empty-state"><div class="profile-empty-state-icon">📋</div>Не в очередях</div>');
                    }

                    // Populate Queue Select
                    const qSelect = $('#addQueueSelect');
                    qSelect.empty().append('<option value="" selected>Выбрать...</option>');
                    if (data.player.all_queues) {
                        data.player.all_queues.forEach(q => {
                            qSelect.append(`<option value="${q.id}">${q.name}</option>`);
                        });
                    }

                    // Store User ID and Role ID
                    $('#editPlayerModal').data('user-id', p.user ? p.user.id : null);
                    $('#editPlayerModal').data('role-id', roleId);
                    $('#editPlayerModal').data('nickname', p.nickname); // Store for use in additions

                    // Load Party Members (КП)
                    loadPartyMembers(roleId);

                } else {
                    $('#editNickname').val('Ошибка загрузки');
                }
            })
            .catch(err => {
                console.error(err);
                $('#editNickname').val('Ошибка');
            });

    } catch (e) { console.error('Error opening modal:', e); }
});

// Helper for Deletions
async function deleteObj(type, id, roleId) {
    if (!confirm('Удалить?')) return;
    let url = '';
    let body = {};

    if (type === 'afk') { url = '/api/afk/delete'; body = { afk_id: id }; }
    else if (type === 'queue') { url = '/api/queue/leave'; body = { entry_id: id }; }
    else if (type === 'char') { url = '/api/character/unlink'; body = { nickname: id }; }

    try {
        await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });
        $(`.edit-player-btn[data-role-id="${roleId}"]`).trigger('click');
    } catch (e) { alert(e); }
}

// Handler for Add Buttons
$(document).ready(function () {
    // Add AFK History
    $('#btnAddHistory').click(async function () {
        const uid = $('#editPlayerModal').data('user-id');
        const rid = $('#editPlayerModal').data('role-id');
        if (!uid) return alert('Сначала привяжите Телеграм ID и сохраните!');

        const s = $('#addHistoryStart').val();
        const e = $('#addHistoryEnd').val();
        if (!s || !e) return alert('Выберите даты');

        try {
            const res = await fetch('/api/afk/add', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ user_id: uid, start: s, end: e })
            });
            const r = await res.json();
            if (r.status !== 'ok') throw new Error(r.message);

            $('#addHistoryStart, #addHistoryEnd').val('');
            $(`.edit-player-btn[data-role-id="${rid}"]`).trigger('click');
        } catch (err) { alert('Ошибка: ' + err.message); }
    });

    // Add Linked Char
    $('#btnAddChar').click(async function () {
        const uid = $('#editPlayerModal').data('user-id');
        const rid = $('#editPlayerModal').data('role-id');
        if (!uid) return alert('Сначала привяжите Телеграм ID и сохраните!');

        const nick = $('#addCharNick').val().trim();
        if (!nick) return alert('Введите ник');

        try {
            const res = await fetch('/api/character/link', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ user_id: uid, nickname: nick })
            });
            const r = await res.json();
            if (r.status !== 'ok') throw new Error(r.message);

            $('#addCharNick').val('');
            $(`.edit-player-btn[data-role-id="${rid}"]`).trigger('click');
        } catch (err) { alert('Ошибка: ' + err.message); }
    });

    // Add To Queue
    $('#btnAddQueue').click(async function () {
        const uid = $('#editPlayerModal').data('user-id');
        const rid = $('#editPlayerModal').data('role-id');
        const curNick = $('#editPlayerModal').data('nickname');
        if (!uid) return alert('Сначала привяжите Телеграм ID и сохраните!');

        const qid = $('#addQueueSelect').val();
        if (!qid) return alert('Выберите очередь');

        // Check mode from button state
        const autoRequeue = $('#queueModeAuto').hasClass('active');

        try {
            const res = await fetch('/api/queue/join', {
                method: 'POST', headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ user_id: uid, queue_id: qid, character_name: curNick, auto_requeue: autoRequeue })
            });
            const r = await res.json();
            if (r.status !== 'ok') throw new Error(r.message);

            $(`.edit-player-btn[data-role-id="${rid}"]`).trigger('click');
        } catch (err) { alert('Ошибка: ' + err.message); }
    });

    // Toggle AFK History visibility
    $('#toggleAfkHistory').click(function () {
        $('#afkDetails').slideToggle();
    });
});

async function savePlayerData() {
    const roleId = $('#editRoleId').val();
    const nickname = $('#editNickname').val().trim();
    const classId = parseInt($('#editClass').val());
    const inClan = $('#editInClan').is(':checked');

    // New Fields
    const telegramId = $('#editTgId').val().trim();
    const isAlt = $('#statusAlt').is(':checked');

    // AFK Dates
    const afkStart = $('#editAfkStart').val(); // YYYY-MM-DD
    const afkEnd = $('#editAfkEnd').val();

    const statusDiv = $('#saveStatus');
    statusDiv.show().removeClass().addClass('alert alert-info py-2 small').text('💾 Сохранение...');

    try {
        const response = await fetch('/api/update_player', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                role_id: roleId,
                nickname: nickname,
                class_id: classId,
                in_clan: inClan,
                telegram_id: telegramId,
                is_alt: isAlt,
                afk_start: afkStart,
                afk_end: afkEnd
            })
        });

        const result = await response.json();

        if (result.status !== 'ok') throw new Error(result.message);

        statusDiv.removeClass().addClass('alert alert-success py-2 small').text('✅ Сохранено!');

        // Reload to reflect changes
        setTimeout(() => window.location.reload(), 500);

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

async function editEventDate(roleId, oldDateStr, oldTimestamp) {
    const newDateStr = prompt("Изменить дату события (YYYY-MM-DD HH:MM:SS):", oldDateStr);
    if (!newDateStr || newDateStr === oldDateStr) return;

    if (!confirm(`Изменить дату на ${newDateStr}?`)) return;

    try {
        const response = await fetch('/api/update_event_date', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                role_id: roleId,
                old_timestamp: oldTimestamp,
                new_date_str: newDateStr
            })
        });

        const result = await response.json();
        if (result.status === 'ok') {
            alert('✅ Дата успешно обновлена!');
            window.location.reload();
        } else {
            alert('❌ Ошибка: ' + result.message);
        }
    } catch (e) {
        alert('❌ Ошибка сети: ' + e.message);
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

/* --- КП (Constant Party) Management --- */

function loadPartyMembers(roleId) {
    const partyCards = $('#partyMembersCards');
    const partyTitle = $('#partyTitle');
    const btnEdit = $('#btnEditPartyName');

    // Reset state
    partyTitle.text('⚔️ Констовая пати (КП)');
    btnEdit.hide();
    partyCards.html('<div class="text-center py-2"><div class="spinner-border spinner-border-sm text-secondary"></div></div>');

    fetch('/api/party/get', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ role_id: roleId })
    })
        .then(r => r.json())
        .then(data => {
            partyCards.empty();

            if (data.status === 'ok' && data.members && data.members.length > 0) {
                // Update Title
                const pName = (data.party && data.party.name) ? data.party.name : 'Констовая пати';
                partyTitle.text(`⚔️ ${pName} (КП)`);

                // Show edit button if leader
                if (data.party && data.party.is_leader) {
                    btnEdit.show();
                    btnEdit.off('click').on('click', function () {
                        const newName = prompt('Введите название КП:', data.party.name || '');
                        if (newName !== null) {
                            renameParty(data.party.id, newName, roleId);
                        }
                    });
                }

                data.members.forEach(m => {
                    const iconId = (m.class_id >= 0 && m.class_id <= 16) ? m.class_id : 0;
                    const leaderBadge = m.is_leader ? '👑' : '';
                    const isSelf = (m.role_id == roleId);

                    // Allow delete if I am leader OR if it is me
                    let showDelete = false;
                    if (data.party.is_leader) showDelete = true;
                    if (isSelf) showDelete = true;

                    let delBtn = showDelete ? `<button class="char-card-delete" onclick="removeFromParty(${m.role_id}, ${roleId})">✖</button>` : '';

                    partyCards.append(`
                    <div class="char-card">
                        ${delBtn}
                        <img class="char-card-icon" src="/static/icons/${iconId}.png" style="width: 32px; height: 32px;">
                        <span class="char-card-name">${leaderBadge} ${m.nickname}</span>
                        <span class="char-card-type">${m.is_leader ? '⭐ Лидер' : '👤 Участник'}</span>
                    </div>
                `);
                });
            } else {
                partyCards.append('<div class="profile-empty-state"><div class="profile-empty-state-icon">⚔️</div>Не состоит в КП</div>');
            }
        })
        .catch(err => {
            console.error('Error loading party:', err);
            partyCards.html('<div class="profile-empty-state text-danger">Ошибка загрузки</div>');
        });
}

function renameParty(partyId, newName, roleId) {
    fetch('/api/party/rename', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ party_id: partyId, name: newName })
    })
        .then(r => r.json())
        .then(data => {
            if (data.status === 'ok') {
                loadPartyMembers(roleId);
            } else {
                alert(data.message || 'Ошибка переименования');
            }
        })
        .catch(err => alert('Ошибка: ' + err));
}

function addToParty() {
    const leaderRoleId = $('#editPlayerModal').data('role-id');
    const nickname = $('#addPartyMemberNick').val().trim();

    if (!nickname) {
        alert('Введите никнейм участника');
        return;
    }

    fetch('/api/party/add', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ leader_role_id: leaderRoleId, nickname: nickname })
    })
        .then(r => r.json())
        .then(data => {
            if (data.status === 'ok') {
                $('#addPartyMemberNick').val('');
                loadPartyMembers(leaderRoleId);
            } else {
                alert(data.message || 'Ошибка добавления');
            }
        })
        .catch(err => alert('Ошибка: ' + err));
}

function removeFromParty(memberRoleId, currentRoleId) {
    if (!confirm('Удалить участника из КП?')) return;

    fetch('/api/party/remove', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ member_role_id: memberRoleId })
    })
        .then(r => r.json())
        .then(data => {
            if (data.status === 'ok') {
                loadPartyMembers(currentRoleId);
            } else {
                alert(data.message || 'Ошибка удаления');
            }
        })
        .catch(err => alert('Ошибка: ' + err));
}

// Bind button click
$(document).ready(function () {
    $('#btnAddPartyMember').on('click', addToParty);
});

/* --- Auth Logic --- */
function logout() {
    fetch('/api/logout', { method: 'POST' })
        .then(() => {
            window.location.reload();
        })
        .catch(err => {
            console.error('Logout failed:', err);
            window.location.reload(); // Reload anyway
        });
}
