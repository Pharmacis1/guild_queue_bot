"use client";

import React, { useEffect, useState, useRef } from 'react';
import { fetchMoneyTable, MoneyTableRow, UserData } from '@/lib/api';
import ClassIcon from '../shared/ClassIcon';
import PlayerTooltip from '../shared/PlayerTooltip';
import GenericTooltip from '../shared/GenericTooltip';
import MassEventModal from '../modals/MassEventModal';

const DAYS_RU = ['Вс', 'Пн', 'Вт', 'Ср', 'Чт', 'Пт', 'Сб'];

const formatPeriod = (start: string, end: string) => {
    if (!start || !end) return '';
    try {
        const sDate = new Date(start);
        const eDate = new Date(end);
        const sStr = sDate.toLocaleDateString('ru-RU');
        const eStr = eDate.toLocaleDateString('ru-RU');
        
        const isSameDay = sDate.getFullYear() === eDate.getFullYear() &&
                          sDate.getMonth() === eDate.getMonth() &&
                          sDate.getDate() === eDate.getDate();

        if (isSameDay) {
            const dayOfWeek = DAYS_RU[sDate.getDay()];
            return `${sStr} (${dayOfWeek})`;
        }
        return `${sStr} — ${eStr}`;
    } catch (e) {
        return `${start} — ${end}`;
    }
};

interface MoneyTableProps {
    onRowClick?: (roleId: number) => void;
    onObserverClick?: (roleId: number, name: string) => void;
    classes?: Record<string, [string, string, string]>;
    currentUser?: UserData | null;
}

export default function MoneyTable({ onRowClick, onObserverClick, classes, currentUser }: MoneyTableProps) {
    const [loading, setLoading] = useState(true);
    const [rows, setRows] = useState<MoneyTableRow[]>([]);
    const [intervals, setIntervals] = useState<{ label: string, start: string, end: string, guild_bonus?: number }[]>([]);
    const [totalGuildBonus, setTotalGuildBonus] = useState(0);
    const [dateRange, setDateRange] = useState({ start: '', end: '' });

    // Filters
    const [search, setSearch] = useState('');
    const [entryType, setEntryType] = useState('ALL'); // ALL, NEW, OLD
    const [afkFilter, setAfkFilter] = useState('ALL'); // ALL, AFK, ONL
    const [period, setPeriod] = useState<string>('WEEK'); // TODAY, WEEK, PREV, CUSTOM
    const [groupPeriod, setGroupPeriod] = useState<string>('day'); // day, week, month
    const [groupCount, setGroupCount] = useState<number>(1);
    const [myCharsOnly, setMyCharsOnly] = useState(false); // Toggle for "My Characters"
    const [selectedClasses, setSelectedClasses] = useState<number[]>([]); // Empty = all classes
    const [showClassDropdown, setShowClassDropdown] = useState(false);
    const [sortConfig, setSortConfig] = useState<{ field: string, order: 'asc' | 'desc' }>({ field: 'total_valor', order: 'desc' });
    const [selectedCpColor, setSelectedCpColor] = useState<string | null>(null);

    // Mass Event State
    const [selectedRoleIds, setSelectedRoleIds] = useState<number[]>([]);
    const [isMassEventModalOpen, setIsMassEventModalOpen] = useState(false);

    const topScrollRef = useRef<HTMLDivElement>(null);
    const tableWrapperRef = useRef<HTMLDivElement>(null);

    // Scroll Sync logic
    useEffect(() => {
        const top = topScrollRef.current;
        const bottom = tableWrapperRef.current;
        if (!top || !bottom) return;

        let isSyncingTop = false;
        let isSyncingBottom = false;

        const handleTopScroll = () => {
            if (!isSyncingBottom) {
                isSyncingTop = true;
                bottom.scrollLeft = top.scrollLeft;
            }
            isSyncingBottom = false;
        };

        const handleBottomScroll = () => {
            if (!isSyncingTop) {
                isSyncingBottom = true;
                top.scrollLeft = bottom.scrollLeft;
            }
            isSyncingTop = false;
        };

        top.addEventListener('scroll', handleTopScroll);
        bottom.addEventListener('scroll', handleBottomScroll);

        return () => {
            top.removeEventListener('scroll', handleTopScroll);
            bottom.removeEventListener('scroll', handleBottomScroll);
        };
    }, [rows, intervals]);

    const fetchData = (params: any = {}) => {
        setLoading(true);
        const queryParams = {
            start: period === 'CUSTOM' ? dateRange.start : '',
            end: period === 'CUSTOM' ? dateRange.end : '',
            period_type: period,
            group_period: groupPeriod,
            group_count: groupCount,
            classes: selectedClasses.length > 0 ? selectedClasses.join(',') : '',
            newcomers: entryType === 'NEW' ? 'only' : entryType === 'OLD' ? 'hide' : undefined,
            ...params
        };

        fetchMoneyTable(queryParams)
            .then((data) => {
                setRows(data.rows);
                setIntervals(data.intervals || []);
                setTotalGuildBonus(data.total_guild_bonus || 0);
                setDateRange({ start: data.start_date, end: data.end_date });

                // Expand all twins by default on first successful load
                if (!initialExpansionDone && data.rows.length > 0) {
                    const allUserIds = new Set(data.rows.map(r => r.user_id).filter((id): id is number => !!id));
                    setExpandedUsers(allUserIds);
                    setInitialExpansionDone(true);
                }
            })
            .catch((err) => console.error("Failed to fetch Money Table:", err))
            .finally(() => setLoading(false));
    };

    useEffect(() => {
        fetchData();
    }, [groupPeriod, groupCount]); // Refetch when grouping changes

    const handleApply = () => {
        fetchData({ start: dateRange.start, end: dateRange.end });
        setPeriod('CUSTOM');
    };

    const handleShortcut = (type: string) => {
        setPeriod(type);
        const now = new Date();
        const utc = now.getTime() + now.getTimezoneOffset() * 60000;
        const mskNow = new Date(utc + 3 * 3600000); // UTC+3
        const today = new Date(mskNow.getFullYear(), mskNow.getMonth(), mskNow.getDate());
        let start = new Date(today);
        let end = new Date(today);

        if (type === 'TODAY') {
            // start = today, end = today
        } else if (type === 'WEEK') {
            const day = today.getDay();
            const diff = today.getDate() - day + (day === 0 ? -6 : 1);
            start.setDate(diff);
            end = new Date(start);
            end.setDate(end.getDate() + 6);
        } else if (type === 'PREV') {
            const day = today.getDay();
            const diff = today.getDate() - day + (day === 0 ? -6 : 1) - 7;
            start.setDate(diff);
            end = new Date(start);
            end.setDate(end.getDate() + 6);
        }

        const fmt = (d: Date) => {
            const y = d.getFullYear();
            const m = String(d.getMonth() + 1).padStart(2, '0');
            const dStr = String(d.getDate()).padStart(2, '0');
            return `${y}-${m}-${dStr}`;
        };
        const sStr = fmt(start);
        const eStr = fmt(end);

        setDateRange({ start: sStr, end: eStr });
        fetchData({ start: sStr, end: eStr });
    };

    const [isInitialLoading, setIsInitialLoading] = useState(true);
    const [expandedUsers, setExpandedUsers] = useState<Set<number>>(new Set());
    const [initialExpansionDone, setInitialExpansionDone] = useState(false);

    useEffect(() => {
        setIsInitialLoading(loading && rows.length === 0);
    }, [loading, rows]);

    const toggleExpand = (userId: number) => {
        const newSet = new Set(expandedUsers);
        if (newSet.has(userId)) {
            newSet.delete(userId);
        } else {
            newSet.add(userId);
        }
        setExpandedUsers(newSet);
    };

    // Client-side filtering
    const filteredRows = rows.filter(r => {
        const matchesSearch = r.name.toLowerCase().includes(search.toLowerCase());
        const matchesType =
            entryType === 'ALL' ? true :
                entryType === 'NEW' ? r.is_newcomer :
                    entryType === 'OLD' ? !r.is_newcomer : true;

        const matchesAfk =
            afkFilter === 'ALL' ? true :
                afkFilter === 'AFK' ? r.is_afk :
                    afkFilter === 'ONL' ? !r.is_afk : true;

        const matchesMyChars = myCharsOnly ? r.is_mine : true;
        const matchesClass = selectedClasses.length === 0 || selectedClasses.includes(r.class_id);
        const matchesCp = selectedCpColor === null || r.cp_color === selectedCpColor;

        return matchesSearch && matchesType && matchesAfk && matchesMyChars && matchesClass && matchesCp;
    });

    const toggleSort = (field: string) => {
        setSortConfig(prev => ({
            field,
            order: prev.field === field && prev.order === 'desc' ? 'asc' : 'desc'
        }));
    };

    // Sort logic
    const sortedFilteredRows = [...filteredRows].sort((a: any, b: any) => {
        const field = sortConfig.field;
        const order = sortConfig.order === 'asc' ? 1 : -1;

        if (field === 'name') {
            return order * a.name.localeCompare(b.name);
        }
        if (field === 'class_id') {
            return order * (a.class_id - b.class_id);
        }

        if (field.startsWith('interval_')) {
            const index = parseInt(field.split('_')[1]);
            const valA = a.interval_stats?.[index]?.valor || 0;
            const valB = b.interval_stats?.[index]?.valor || 0;
            if (valA !== valB) return order * (valA - valB);
        } else if (a[field] !== undefined && b[field] !== undefined) {
            if (typeof a[field] === 'string') {
                return order * a[field].localeCompare(b[field]);
            }
            return order * (a[field] - b[field]);
        }

        return b.total_valor - a.total_valor;
    });

    // Grouping Logic:
    // 1. Identify "groups" based on user_id.
    // 2. If user_id is null, it's a standalone group.
    // 3. If user_id present, collect all chars.
    // 4. Sort the GROUPS based on the SORTED FILTERED ROWS order of their MAIN char (or best char if no main).

    // Helper to find the "representative" row for a user_id group from the sorted list
    // We want to respect the current sort order. So the "rank" of a group is the index of its First Appearing Member in the sorted list.

    // But wait, if we group, we must show Main first? Or just show the structure?
    // Requirement: "Twins always show under mains".
    // So Main is the anchor.
    // If Main is filtered out? We might need to show hidden main? Or just show twin as standalone if main is missing?
    // Let's assume we operate on the FULL dataset for grouping, then filter? 
    // No, filtering removes rows. If I filter by "Archer", and Main is "Warrior", I only see twin.
    // In that case, maybe grouping shouldn't apply or it should just show the twin.
    // "Show twins under mains" implies a hierarchical view.
    // Let's go with: Group visible rows. If multiple rows share a user_id:
    //   - Find the "Main" among them (is_alt=false).
    //   - If Valid Main exists in visible rows, put it first. Others under it.
    //   - If NO Main in visible rows (e.g. filtered out), just pick the first one as anchor? 
    //   - Or maybe we should allow expanding to see ALL twins even if filtered? 
    //      -> Complex. Standard table filtering usually hides non-matching.
    // Let's stick to: Group visible rows by user_id.

    const columnMaxes = React.useMemo(() => {
        const maxes: number[] = [];
        if (rows.length === 0) return [];
        const stageCount = rows[0].interval_stats?.length || 0;
        for (let i = 0; i < stageCount; i++) {
            maxes.push(Math.max(1, ...rows.map(r => r.interval_stats?.[i]?.valor || 0)));
        }
        return maxes;
    }, [rows]);

    const finalDisplayRows: MoneyTableRow[] = [];

    const processedUserIds = new Set<number>();
    console.log("Building finalDisplayRows from", sortedFilteredRows.length, "rows");


    // We iterate through the SORTED rows.
    for (const row of sortedFilteredRows) {
        if (row.user_id) {
            if (processedUserIds.has(row.user_id)) continue; // Already handled this group
            processedUserIds.add(row.user_id);

            // Find all visible rows for this user
            const groupRows = sortedFilteredRows.filter(r => r.user_id === row.user_id);

            // Find Main
            const mainRow = groupRows.find(r => !r.is_alt);
            const anchor = mainRow || groupRows[0];
            const others = groupRows.filter(r => r !== anchor).map(r => ({ ...r, _is_child: true }));

            // Add Anchor
            finalDisplayRows.push(anchor);

            // If expanded, add others
            if (expandedUsers.has(row.user_id) && others.length > 0) {
                finalDisplayRows.push(...others);
            }
        } else {
            // Standalone
            finalDisplayRows.push(row);
        }
    }

    const maxTotalValor = Math.max(1, ...sortedFilteredRows.map(r => r.total_valor));


    const getSortIcon = (field: string) => {

        if (sortConfig.field !== field) return '♦';
        return sortConfig.order === 'desc' ? '▼' : '▲';
    };

    return (
        <div className="table-container fade-in-smooth" style={{ maxWidth: '1200px', margin: '0 auto' }}>
            {/* Control Deck */}
            <div className="control-deck" style={{
                width: '100%',
                boxSizing: 'border-box',
                marginBottom: '16px',
                background: 'linear-gradient(145deg, rgba(25, 25, 25, 0.9), rgba(10, 10, 10, 0.95))',
                backdropFilter: 'blur(16px)',
                border: '1px solid rgba(255, 255, 255, 0.08)',
                borderTop: '1px solid rgba(255, 255, 255, 0.15)',
                boxShadow: '0 15px 40px rgba(0, 0, 0, 0.6)',
                borderRadius: '12px',
                padding: '8px 16px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                gap: '8px',
                position: 'relative',
                zIndex: 100,
                flexWrap: 'wrap' // Allow wrapping if screen is small
            }}>
                {/* Modals */}
                <MassEventModal 
                    isOpen={isMassEventModalOpen} 
                    onClose={() => setIsMassEventModalOpen(false)}
                    onSuccess={() => {
                        setIsMassEventModalOpen(false);
                        setSelectedRoleIds([]);
                        fetchData({ start: dateRange.start, end: dateRange.end }); // Refresh data
                    }}
                    selectedRoleIds={selectedRoleIds}
                />

                {/* Left Group */}
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px', flexWrap: 'wrap' }}>
                    {/* Bulk Action Button */}
                    {selectedRoleIds.length > 0 && currentUser?.is_master && (
                        <button
                            className="btn btn-sm fade-in-smooth"
                            style={{
                                background: 'rgba(255, 69, 0, 0.2)',
                                border: '1px solid rgba(255, 69, 0, 0.5)',
                                color: '#fff',
                                height: '32px',
                                padding: '0 12px',
                                borderRadius: '6px',
                                display: 'flex',
                                alignItems: 'center',
                                gap: '6px',
                                fontWeight: 'bold'
                            }}
                            onClick={() => setIsMassEventModalOpen(true)}
                        >
                            <span style={{ fontSize: '1.2rem' }}>⚡</span>
                            Масс. Событие ({selectedRoleIds.length})
                        </button>
                    )}

                    {/* Clear CP Filter Button */}
                    {selectedCpColor && (
                        <button
                            className="btn btn-sm fade-in-smooth"
                            style={{
                                background: `rgba(20, 20, 20, 0.8)`,
                                border: `1px solid ${selectedCpColor}`,
                                color: '#fff',
                                height: '32px',
                                padding: '0 8px',
                                borderRadius: '6px',
                                display: 'flex',
                                alignItems: 'center',
                                gap: '6px'
                            }}
                            title="Сбросить фильтр КП"
                            onClick={() => setSelectedCpColor(null)}
                        >
                            <div style={{ width: '10px', height: '10px', borderRadius: '50%', background: selectedCpColor, boxShadow: `0 0 5px ${selectedCpColor}` }} />
                            <span style={{ fontSize: '1.2rem', lineHeight: 0.5, paddingBottom: '2px' }}>×</span>
                        </button>
                    )}

                    {/* Class Filter */}
                    <div style={{ position: 'relative' }}>
                        <button
                            className="btn btn-sm"
                            style={{
                                background: selectedClasses.length > 0 ? 'rgba(209, 0, 31, 0.3)' : 'transparent',
                                border: '1px solid #444',
                                color: selectedClasses.length > 0 ? '#fff' : '#888',
                                height: '32px',
                                padding: '0 12px',
                                borderRadius: '6px'
                            }}
                            onClick={() => setShowClassDropdown(!showClassDropdown)}
                        >
                            🛡️ {selectedClasses.length > 0 && <span style={{ marginLeft: '4px', fontSize: '0.7rem' }}>{selectedClasses.length}</span>}
                        </button>
                        {showClassDropdown && (
                            <div style={{
                                position: 'absolute',
                                top: '36px',
                                left: 0,
                                background: 'rgba(20, 20, 20, 0.98)',
                                border: '1px solid rgba(255, 255, 255, 0.15)',
                                borderRadius: '8px',
                                padding: '8px',
                                zIndex: 1000,
                                minWidth: '200px',
                                maxHeight: '300px',
                                overflowY: 'auto'
                            }}>
                                <div style={{ display: 'flex', gap: '8px', marginBottom: '8px', borderBottom: '1px solid #333', paddingBottom: '8px' }}>
                                    <button
                                        className="btn btn-xs"
                                        style={{ flex: 1, background: 'transparent', border: '1px solid #555', color: '#aaa', fontSize: '0.7rem' }}
                                        onClick={() => {
                                            const uniqueClasses = Array.from(new Set(rows.map(r => r.class_id))).filter(id => id >= 0);
                                            setSelectedClasses(uniqueClasses);
                                        }}
                                    >SELECT ALL</button>
                                    <button
                                        className="btn btn-xs"
                                        style={{ flex: 1, background: 'transparent', border: '1px solid #555', color: '#aaa', fontSize: '0.7rem' }}
                                        onClick={() => setSelectedClasses([])}
                                    >CLEAR</button>
                                </div>
                                {Array.from(new Set(rows.map(r => r.class_id))).filter(id => id >= 0).sort((a, b) => a - b).map(classId => (
                                    <label
                                        key={classId}
                                        style={{
                                            display: 'flex',
                                            alignItems: 'center',
                                            gap: '8px',
                                            padding: '4px 8px',
                                            cursor: 'pointer',
                                            color: '#ccc',
                                            fontSize: '0.8rem'
                                        }}
                                    >
                                        <input
                                            type="checkbox"
                                            checked={selectedClasses.includes(classId)}
                                            onChange={() => {
                                                if (selectedClasses.includes(classId)) {
                                                    setSelectedClasses(selectedClasses.filter(c => c !== classId));
                                                } else {
                                                    setSelectedClasses([...selectedClasses, classId]);
                                                }
                                            }}
                                        />
                                        <ClassIcon classId={classId} size={16} />
                                        <span>{classes?.[classId.toString()]?.[0] || `Class ${classId}`}</span>
                                    </label>
                                ))}
                                <button
                                    className="btn btn-sm"
                                    style={{
                                        width: '100%',
                                        marginTop: '8px',
                                        background: 'var(--accent-ruby)',
                                        border: 'none',
                                        color: '#fff',
                                        fontSize: '0.75rem'
                                    }}
                                    onClick={() => setShowClassDropdown(false)}
                                >OK</button>
                            </div>
                        )}
                    </div>

                    {/* Toggle My Chars */}
                    <div
                        className="btn-toggle-wrapper"
                        style={{
                            display: 'flex', alignItems: 'center', gap: '8px',
                            cursor: 'pointer',
                            opacity: myCharsOnly ? 1 : 0.5,
                            transition: 'opacity 0.2s'
                        }}
                        onClick={() => setMyCharsOnly(!myCharsOnly)}
                    >
                        <span style={{ fontSize: '1.2rem' }}>👤</span>
                        <div style={{
                            width: '36px', height: '18px',
                            background: myCharsOnly ? 'var(--accent-ruby)' : '#333',
                            borderRadius: '10px',
                            position: 'relative',
                            transition: 'background 0.2s'
                        }}>
                            <div style={{
                                width: '14px', height: '14px',
                                background: '#fff',
                                borderRadius: '50%',
                                position: 'absolute',
                                top: '2px',
                                left: myCharsOnly ? '20px' : '2px',
                                transition: 'left 0.2s'
                            }} />
                        </div>
                    </div>

                    {/* Grouping Controls */}
                    <div style={{ display: 'flex', alignItems: 'center', background: '#111', borderRadius: '6px', padding: '2px' }}>
                        <select
                            value={groupPeriod}
                            onChange={(e) => setGroupPeriod(e.target.value)}
                            style={{
                                background: '#111',
                                border: 'none',
                                color: '#eee',
                                padding: '0 8px',
                                height: '28px',
                                fontSize: '0.75rem',
                                outline: 'none',
                                textTransform: 'uppercase',
                                cursor: 'pointer',
                                fontWeight: 700
                            }}
                        >
                            <option value="day" style={{ background: '#222', color: '#fff' }}>DAY</option>
                            <option value="week" style={{ background: '#222', color: '#fff' }}>WEEK</option>
                            <option value="month" style={{ background: '#222', color: '#fff' }}>MONTH</option>
                        </select>
                        <input
                            type="number"
                            min="1"
                            max="30"
                            value={groupCount}
                            onChange={(e) => setGroupCount(parseInt(e.target.value) || 1)}
                            style={{
                                background: 'transparent',
                                border: 'none',
                                color: '#eee',
                                width: '30px',
                                textAlign: 'center',
                                height: '28px',
                                fontSize: '0.75rem',
                                outline: 'none',
                                borderLeft: '1px solid #333'
                            }}
                        />
                    </div>

                    {/* Preset Buttons */}
                    <div className="btn-group" style={{ display: 'flex', background: '#111', borderRadius: '6px', padding: '2px', gap: '1px' }}>
                        {['TODAY', 'WEEK', 'PREV'].map(r => (
                            <button
                                key={r}
                                onClick={() => handleShortcut(r)}
                                style={{
                                    background: period === r ? 'var(--accent-ruby)' : 'transparent',
                                    color: period === r ? '#fff' : '#666',
                                    border: 'none',
                                    padding: '4px 8px',
                                    borderRadius: '4px',
                                    fontSize: '0.75rem',
                                    fontWeight: 700,
                                    textTransform: 'uppercase',
                                    cursor: 'pointer'
                                }}
                            >
                                {r}
                            </button>
                        ))}
                    </div>

                    {/* Newcomers Filter - Tactical Segmented */}
                    <div className="btn-group" style={{ display: 'flex', background: '#111', borderRadius: '6px', padding: '2px', border: '1px solid #333' }}>
                        {['ALL', 'NEW', 'OLD'].map(t => (
                            <button
                                key={t}
                                onClick={() => setEntryType(t)}
                                style={{
                                    background: entryType === t ? 'var(--accent-ruby)' : 'transparent',
                                    color: entryType === t ? '#fff' : '#666',
                                    border: 'none',
                                    padding: '4px 10px',
                                    borderRadius: '4px',
                                    fontSize: '0.7rem',
                                    fontWeight: 700,
                                    textTransform: 'uppercase',
                                    cursor: 'pointer',
                                    minWidth: '40px'
                                }}
                            >
                                {t}
                            </button>
                        ))}
                    </div>

                    {/* AFK Filter - Tactical Segmented */}
                    <div className="btn-group" style={{ display: 'flex', background: '#111', borderRadius: '6px', padding: '2px', border: '1px solid #333' }}>
                        {['ALL', 'AFK', 'ONL'].map(s => (
                            <button
                                key={s}
                                onClick={() => setAfkFilter(s)}
                                style={{
                                    background: afkFilter === s ? 'var(--accent-ruby)' : 'transparent',
                                    color: afkFilter === s ? '#fff' : '#666',
                                    border: 'none',
                                    padding: '4px 8px',
                                    borderRadius: '4px',
                                    fontSize: '0.7rem',
                                    fontWeight: 700,
                                    textTransform: 'uppercase',
                                    cursor: 'pointer',
                                    minWidth: '36px'
                                }}
                            >
                                {s}
                            </button>
                        ))}
                    </div>
                </div>

                {/* Right Group: Date Inputs & Apply */}
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px', marginLeft: 'auto', flexWrap: 'wrap' }}>
                    <div style={{ display: 'flex', alignItems: 'center', background: '#111', borderRadius: '6px', padding: '0 8px', border: '1px solid #333' }}>
                        <span style={{ fontSize: '0.7rem', color: '#666', marginRight: '6px', textTransform: 'uppercase' }}>FROM</span>
                        <input
                            type="date"
                            value={dateRange.start}
                            onChange={(e) => setDateRange({ ...dateRange, start: e.target.value })}
                            style={{ background: 'transparent', border: 'none', color: '#fff', fontSize: '0.8rem', padding: '4px 0', outline: 'none' }}
                        />
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', background: '#111', borderRadius: '6px', padding: '0 8px', border: '1px solid #333' }}>
                        <span style={{ fontSize: '0.7rem', color: '#666', marginRight: '6px', textTransform: 'uppercase' }}>TO</span>
                        <input
                            type="date"
                            value={dateRange.end}
                            onChange={(e) => setDateRange({ ...dateRange, end: e.target.value })}
                            style={{ background: 'transparent', border: 'none', color: '#fff', fontSize: '0.8rem', padding: '4px 0', outline: 'none' }}
                        />
                    </div>

                    <button
                        onClick={handleApply}
                        className="btn"
                        style={{
                            background: 'var(--accent-ruby)',
                            color: '#fff',
                            border: 'none',
                            padding: '4px 12px',
                            borderRadius: '6px',
                            fontSize: '0.8rem',
                            fontWeight: 700
                        }}
                    >OK</button>
                </div>
            </div>

            {/* Top Scrollbar (Dummy) */}
            <div
                ref={topScrollRef}
                className="kh-table-wrapper"
                style={{
                    overflowX: 'auto',
                    maxWidth: '1200px',
                    margin: '0 auto',
                    border: 'none',
                    background: 'transparent',
                    marginBottom: '4px',
                    height: '12px'
                }}
            >
                <div style={{
                    width: intervals.length > 10 ? `${250 + (intervals.length * 60) + 100}px` : '100%',
                    height: '1px'
                }}></div>
            </div>

            {/* Scrollable Container Wrapper */}
            <div
                ref={tableWrapperRef}
                className="kh-table-wrapper"
                style={{
                    overflowX: 'auto',
                    maxWidth: '1200px',
                    margin: '0 auto',
                    border: '1px solid rgba(255, 255, 255, 0.15)',
                    borderRadius: '8px',
                    background: 'rgba(5, 5, 5, 1)',
                    backdropFilter: 'blur(5px)',
                    position: 'relative'
                }}
            >
                <div className="kh-table-body" style={{
                    border: 'none',
                    borderRadius: '0',
                    minWidth: '100%',
                    width: intervals.length > 10 ? 'max-content' : '100%',
                    maxWidth: 'none',
                    margin: '0',
                    background: 'rgba(5, 5, 5, 1)'
                }}>
                    <div className="kh-table-header" style={{
                        display: 'grid',
                        gridTemplateColumns: intervals.length > 10
                            ? `250px repeat(${intervals.length}, 60px) 100px`
                            : `minmax(200px, 2.5fr) repeat(${intervals.length}, 1fr) 1fr`,
                        padding: '0',
                        gap: '0',
                        width: '100%',
                        maxWidth: 'none',
                        margin: '0 auto',
                        boxSizing: 'border-box',
                        color: '#fff',
                        fontWeight: 700,
                        fontSize: '0.85rem',
                        textTransform: 'uppercase',
                        alignItems: 'center',
                        position: 'sticky',
                        top: 0,
                        zIndex: 20,
                        backgroundColor: 'rgba(5, 5, 5, 1)',
                        borderTop: 'none',
                        borderLeft: 'none',
                        borderRight: 'none'
                    }}>
                        <div
                            className="kh-col kh-participant sticky-col"
                            onClick={() => toggleSort('name')}
                            style={{
                                cursor: 'pointer',
                                userSelect: 'none',
                                paddingLeft: '16px',
                                position: 'sticky',
                                left: 0,
                                zIndex: 30,
                                background: 'rgba(5, 5, 5, 1)',
                                height: '100%',
                                boxSizing: 'border-box'
                            }}
                        >
                            <ClassIcon classId={0} size={20} />
                            <span>УЧАСТНИК</span>
                            <span style={{
                                fontSize: '0.7rem',
                                marginLeft: '4px',
                                color: sortConfig.field === 'name' ? 'var(--accent-ruby)' : 'rgba(255,255,255,0.3)'
                            }}>{getSortIcon('name')}</span>
                        </div>

                        {intervals.map((interval, i) => (
                            <div
                                key={i}
                                className="kh-col kh-stage"
                                style={{ justifyContent: 'center', color: '#ccc', cursor: 'pointer', userSelect: 'none' }}
                                onClick={() => toggleSort(`interval_${i}`)}
                            >
                                {interval.label}
                                <span style={{
                                    fontSize: '0.6rem',
                                    marginLeft: '2px',
                                    color: sortConfig.field === `interval_${i}` ? 'var(--accent-ruby)' : 'rgba(255,255,255,0.2)'
                                }}>{getSortIcon(`interval_${i}`)}</span>
                            </div>
                        ))}

                        <div
                            className="kh-col kh-stage"
                            onClick={() => toggleSort('total_valor')}
                            style={{ cursor: 'pointer', userSelect: 'none', color: '#fff', justifyContent: 'center' }}
                        >
                            СУММА
                            <span style={{
                                fontSize: '0.6rem',
                                marginLeft: '2px',
                                color: sortConfig.field === 'total_valor' ? 'var(--accent-ruby)' : 'rgba(255,255,255,0.2)'
                            }}>{getSortIcon('total_valor')}</span>
                        </div>
                    </div>

                    {/* Table Body */}
                    <div className={loading && rows.length > 0 ? "loading-blur" : ""}>
                        {isInitialLoading ? (
                            Array.from({ length: 15 }).map((_, i) => (
                                <div key={i} className="kh-row skeleton-row" style={{
                                    display: 'grid',
                                    gridTemplateColumns: `2.5fr repeat(${intervals.length || 7}, 1fr) 1fr`,
                                    paddingRight: '16px',
                                    gap: '4px',
                                    width: '100%',
                                    maxWidth: 'none',
                                    margin: '0',
                                    boxSizing: 'border-box',
                                    borderBottom: '1px solid rgba(255, 255, 255, 0.05)',
                                    minHeight: '44px',
                                    alignItems: 'center'
                                }}>
                                    <div className="kh-col kh-participant" style={{ gap: '10px', paddingLeft: '16px' }}>
                                        {/* Ghost Row */}
                                    </div>
                                    {Array.from({ length: (intervals.length || 7) + 1 }).map((_, j) => (
                                        <div key={j} className="kh-col"></div>
                                    ))}
                                </div>
                            ))
                        ) : (
                            (() => {
                                const columnMaxes = intervals.map((_, i) => {
                                    let max = 0;
                                    finalDisplayRows.forEach(row => {
                                        if (row.interval_stats && row.interval_stats[i]) {
                                            if (row.interval_stats[i].valor > max) max = row.interval_stats[i].valor;
                                        }
                                    });
                                    return max;
                                });

                                return finalDisplayRows.map((row) => {
                                    let rowBg = 'transparent';
                                    let stickyStyle: React.CSSProperties = {
                                        background: 'rgba(5, 5, 5, 1)'
                                    };

                                    if (row.is_newcomer) {
                                        stickyStyle = {
                                            backgroundColor: 'rgba(5, 5, 5, 1)',
                                            backgroundImage: 'linear-gradient(to right, rgba(64, 224, 208, 0.15) 0%, transparent 85%)'
                                        };
                                    } else if (row.is_afk) {
                                        stickyStyle = {
                                            backgroundColor: 'rgba(5, 5, 5, 1)',
                                            backgroundImage: 'linear-gradient(to right, rgba(128, 128, 128, 0.15) 0%, transparent 85%)'
                                        };
                                    } else if (row.is_mine) {
                                        stickyStyle = {
                                            backgroundColor: 'rgba(5, 5, 5, 1)',
                                            backgroundImage: 'linear-gradient(to right, rgba(50, 205, 50, 0.15) 0%, transparent 85%)'
                                        };
                                    }

                                    // Check if this row is part of a group and if it's main or alt
                                    const isGroupHead = row.user_id && !row.is_alt; // Simplified assumption for display logic based on our sorting
                                    // Actually, we rely on finalDisplayRows order. 
                                    // If row is !is_alt and has user_id, it MIGHT have twins.
                                    // But we need to know if there ARE twins to show the expand button.
                                    // We can just check original sortedFilteredRows
                                    const isExpanded = row.user_id ? expandedUsers.has(row.user_id) : false;
                                    const hasTwins = row.user_id ? sortedFilteredRows.filter(r => r.user_id === row.user_id).length > 1 : false;
                                    const isGroupAnchor = row.user_id && !row.is_alt && hasTwins;
                                    const isChild = !!(row as any)._is_child;
                                    const participantAllocatedPadding = isChild ? '64px' : '16px';

                                    // CP Neon Strip setup
                                    const cpColor = row.cp_color;
                                    const customStickyStyle = { ...stickyStyle };

                                    const isSelected = selectedRoleIds.includes(row.role_id);
                                    const finalRowBg = isSelected ? 'rgba(255, 69, 0, 0.2)' : rowBg;
                                    if (isSelected) {
                                        customStickyStyle.background = 'rgba(255, 69, 0, 0.2)';
                                    }

                                    return (
                                        <div
                                            key={row.role_id}
                                            className={`kh-row fade-in-smooth kh-row-interactive ${row.is_mine ? 'my-row' : ''} ${row.is_afk ? 'afk-row' : ''} ${row.is_newcomer ? 'newcomer-row' : ''} ${isSelected ? 'selected-row' : ''}`}
                                            onClick={(e) => {
                                                if (currentUser?.is_master && (e.ctrlKey || e.metaKey)) {
                                                    e.preventDefault();
                                                    setSelectedRoleIds(prev => 
                                                        prev.includes(row.role_id) 
                                                            ? prev.filter(id => id !== row.role_id) 
                                                            : [...prev, row.role_id]
                                                    );
                                                }
                                            }}
                                            style={{
                                                display: 'grid',
                                                gridTemplateColumns: intervals.length > 10
                                                    ? `250px repeat(${intervals.length}, 60px) 100px`
                                                    : `minmax(200px, 2.5fr) repeat(${intervals.length}, 1fr) 1fr`,
                                                paddingRight: '0',
                                                gap: '0',
                                                width: '100%',
                                                maxWidth: 'none',
                                                margin: '0 auto',
                                                boxSizing: 'border-box',
                                                background: finalRowBg, // Soft gradient for the rest of the row
                                                borderBottom: '1px solid rgba(255, 255, 255, 0.05)',
                                                alignItems: 'stretch',
                                                cursor: currentUser?.is_master ? 'pointer' : 'default',
                                                userSelect: 'none',
                                                fontSize: isChild ? '0.9em' : '1em',
                                                opacity: isChild ? 0.9 : 1
                                            }}
                                        >
                                            {/* Participant */}
                                            <div className="kh-col kh-participant sticky-col" style={{
                                                ...customStickyStyle,
                                                padding: `10px ${16}px 10px ${participantAllocatedPadding}`,
                                                display: 'flex',
                                                alignItems: 'center',
                                                gap: '8px',
                                                height: '100%',
                                                boxSizing: 'border-box',
                                                position: 'sticky',
                                                left: 0,
                                                zIndex: 10,
                                                borderRight: 'none',
                                                backdropFilter: 'blur(10px)'
                                            }}>
                                                {/* CP Neon Strip rendered as separate block */}
                                                {cpColor && (
                                                    <div
                                                        title={selectedCpColor === cpColor ? "Сбросить фильтр КП" : "Фильтр по этой КП"}
                                                        onClick={(e) => {
                                                            e.stopPropagation();
                                                            setSelectedCpColor(prev => prev === cpColor ? null : cpColor);
                                                        }}
                                                        style={{
                                                            position: 'absolute',
                                                            left: 0,
                                                            top: 0,
                                                            bottom: 0,
                                                            width: '4px',
                                                            background: cpColor,
                                                            boxShadow: selectedCpColor === cpColor ? `0 0 15px 2px ${cpColor}` : `0 0 10px ${cpColor}`,
                                                            cursor: 'pointer',
                                                            zIndex: 12,
                                                            transition: 'all 0.2s',
                                                            opacity: selectedCpColor && selectedCpColor !== cpColor ? 0.3 : 1
                                                        }} />
                                                )}

                                                <ClassIcon classId={row.class_id} size={isChild ? 20 : 24} />
                                                <PlayerTooltip
                                                    joinDate={row.join_date}
                                                    joinDaysAgo={row.join_days_ago}
                                                    isAfk={row.is_afk}
                                                    afkDates={row.afk_dates}
                                                    afkReason={row.afk_reason}
                                                    mainNickname={row.main_nickname}
                                                    parties={row.parties}
                                                >
                                                    <span
                                                        className="player-name"
                                                        style={{
                                                            marginRight: '4px',
                                                            whiteSpace: 'nowrap',
                                                            cursor: currentUser?.is_master ? 'pointer' : 'default',
                                                            color: isChild ? '#ccc' : '#fff'
                                                        }}
                                                        onClick={(e) => {
                                                            if (currentUser?.is_master && onRowClick) {
                                                                if (!(e.ctrlKey || e.metaKey)) {
                                                                    e.stopPropagation();
                                                                    onRowClick(row.role_id);
                                                                }
                                                            }
                                                        }}
                                                    >{row.name}</span>
                                                    {hasTwins && !isChild && (
                                                        <span
                                                            onClick={(e) => {
                                                                e.stopPropagation();
                                                                if (row.user_id) toggleExpand(row.user_id);
                                                            }}
                                                            style={{
                                                                cursor: 'pointer',
                                                                fontSize: '10px',
                                                                color: '#888',
                                                                marginLeft: '8px',
                                                                display: 'inline-flex',
                                                                alignItems: 'center',
                                                                justifyContent: 'center',
                                                                transition: 'all 0.2s',
                                                                transform: isExpanded ? 'rotate(180deg)' : 'rotate(0deg)',
                                                                padding: '2px',
                                                                border: '1px solid #444',
                                                                borderRadius: '3px',
                                                                background: 'rgba(255,255,255,0.05)',
                                                                width: '18px',
                                                                height: '18px',
                                                                lineHeight: 1
                                                            }}
                                                        >
                                                            ▼
                                                        </span>
                                                    )}
                                                </PlayerTooltip>
                                                {onObserverClick && currentUser?.is_master && (
                                                    <button
                                                        onClick={(e) => {
                                                            e.stopPropagation();
                                                            onObserverClick(row.role_id, row.name);
                                                        }}
                                                        className="btn-observer-spider"
                                                        title="View Equipment"
                                                        style={{
                                                            background: 'none',
                                                            border: 'none',
                                                            cursor: 'pointer',
                                                            fontSize: '0.85rem',
                                                            padding: 0,
                                                            lineHeight: 1,
                                                            opacity: 0.15,
                                                            filter: 'grayscale(100%) brightness(0.7)'
                                                        }}
                                                        onMouseOver={(e) => {
                                                            e.currentTarget.style.opacity = '0.8';
                                                            e.currentTarget.style.filter = 'none';
                                                        }}
                                                        onMouseOut={(e) => {
                                                            e.currentTarget.style.opacity = '0.15';
                                                            e.currentTarget.style.filter = 'grayscale(100%) brightness(0.7)';
                                                        }}
                                                    >
                                                        🕷️
                                                    </button>
                                                )}
                                            </div>

                                            {/* Interval Data */}
                                            {
                                                row.interval_stats?.map((stat, i) => {
                                                    const isZero = stat.valor === 0;
                                                    let bg = `rgba(139, 0, 0, ${0.15 + (stat.valor / (columnMaxes[i] || 1)) * 0.35})`;
                                                    let boxShadow = `0 0 10px rgba(139, 0, 0, ${0.1 + (stat.valor / (columnMaxes[i] || 1)) * 0.2})`;
                                                    let border = 'none';
                                                    let color = '#fff';

                                                    if (stat.is_newcomer_stay) {
                                                        bg = 'rgba(64, 224, 208, 0.2)';
                                                        boxShadow = 'none';
                                                        border = '1px solid rgba(64, 224, 208, 0.3)';
                                                        color = '#fff';
                                                    } else if (stat.is_afk_stay) {
                                                        bg = 'rgba(100, 100, 100, 0.4)';
                                                        boxShadow = 'none';
                                                        border = '1px solid rgba(120, 120, 120, 0.5)';
                                                    }

                                                    if (stat.is_pre_join) {
                                                        color = '#444';
                                                        bg = 'transparent';
                                                        boxShadow = 'none';
                                                        border = 'none';
                                                    } else if (stat.valor === 0 && !stat.is_newcomer_stay && !stat.is_afk_stay) {
                                                        color = '#666';
                                                    }

                                                    return (
                                                        <div key={i} className="kh-col kh-stage" style={{ justifyContent: 'center' }}>
                                                            {stat.is_pre_join ? (
                                                                <span style={{ opacity: 0.15, fontSize: '1.2rem' }}>—</span>
                                                            ) : isZero && !stat.is_newcomer_stay && !stat.is_afk_stay ? (
                                                                <span style={{ opacity: 0.2, fontSize: '0.8rem' }}>0</span>
                                                            ) : (
                                                                <GenericTooltip
                                                                    title="Детализация по периоду"
                                                                    content={[formatPeriod(intervals[i].start, intervals[i].end), ...(stat.valor_details || [])]}
                                                                >
                                                                    <span style={{
                                                                        background: bg,
                                                                        color: color,
                                                                        width: '34px',
                                                                        height: '34px',
                                                                        display: 'flex',
                                                                        alignItems: 'center',
                                                                        justifyContent: 'center',
                                                                        borderRadius: '4px',
                                                                        fontSize: '0.9rem',
                                                                        fontWeight: 700,
                                                                        boxShadow: boxShadow,
                                                                        border: border,
                                                                        textAlign: 'center'
                                                                    }}>
                                                                        {stat.is_pre_join ? '-' : stat.valor.toLocaleString()}
                                                                    </span>
                                                                </GenericTooltip>
                                                            )}
                                                        </div>
                                                    );
                                                })
                                            }

                                            {/* TOTAL SUM */}
                                            <div className="kh-col kh-stage" style={{ justifyContent: 'center' }}>
                                                <span style={{
                                                    background: `rgba(139, 0, 0, ${0.08 + (row.total_valor / maxTotalValor) * 0.22})`,
                                                    color: '#fff',
                                                    width: '34px',
                                                    height: '34px',
                                                    display: 'flex',
                                                    alignItems: 'center',
                                                    justifyContent: 'center',
                                                    // padding: '0 12px', // Removed padding to force square
                                                    minWidth: 'auto', // Removed minWidth
                                                    borderRadius: '4px',
                                                    fontSize: '0.9rem',
                                                    fontWeight: 700,
                                                    boxShadow: `0 0 10px rgba(139, 0, 0, ${0.05 + (row.total_valor / maxTotalValor) * 0.15})`
                                                }}>
                                                    {row.total_valor.toLocaleString()}
                                                </span>
                                            </div>
                                        </div>
                                    );
                                });
                            })()
                        )}

                    {!loading && filteredRows.length > 0 && (
                        <div className="kh-row total-row" style={{
                            display: 'grid',
                            gridTemplateColumns: intervals.length > 10
                                ? `250px repeat(${intervals.length}, 60px) 100px`
                                : `minmax(200px, 2.5fr) repeat(${intervals.length}, 1fr) 1fr`,
                            gap: '0',
                            padding: '0',
                            width: '100%',
                            maxWidth: 'none',
                            margin: '0 auto',
                            boxSizing: 'border-box',
                            background: 'rgba(255, 255, 255, 0.03)',
                            borderTop: '1px solid rgba(255, 255, 255, 0.15)',
                            minHeight: '44px',
                            alignItems: 'stretch',
                            fontWeight: 'bold',
                            color: '#fff'
                        }}>
                            <div className="kh-col sticky-col" style={{
                                padding: '10px 16px',
                                fontSize: '0.9rem',
                                color: 'var(--accent-ruby)',
                                position: 'sticky',
                                left: 0,
                                zIndex: 30,
                                background: 'rgba(5, 5, 5, 1)',
                                height: '100%',
                                display: 'flex',
                                alignItems: 'center',
                                boxSizing: 'border-box',
                                borderRight: '1px solid rgba(255, 255, 255, 0.05)'
                            }}>
                                ИТОГО
                            </div>

                             {intervals.map((interval, i) => {
                                const playerSum = filteredRows.reduce((acc, r) => acc + (r.interval_stats?.[i]?.valor || 0), 0);
                                const bonus = interval.guild_bonus || 0;
                                const sum = playerSum + bonus;
                                
                                const s1_count = filteredRows.reduce((acc, r) => acc + (r.interval_stats?.[i]?.s1 || 0), 0);
                                const s2_count = filteredRows.reduce((acc, r) => acc + (r.interval_stats?.[i]?.s2 || 0), 0);
                                const s3_count = filteredRows.reduce((acc, r) => acc + (r.interval_stats?.[i]?.s3 || 0), 0);
                                const s4_count = filteredRows.reduce((acc, r) => acc + (r.interval_stats?.[i]?.s4 || 0), 0);
                                const s5_count = filteredRows.reduce((acc, r) => acc + (r.interval_stats?.[i]?.s5 || 0), 0);
                                const s6_count = filteredRows.reduce((acc, r) => acc + (r.interval_stats?.[i]?.s6 || 0), 0);
                                const s7_count = filteredRows.reduce((acc, r) => acc + (r.interval_stats?.[i]?.s7 || 0), 0);
                                const adepts_count = filteredRows.reduce((acc, r) => acc + (r.interval_stats?.[i]?.adepts || 0), 0);

                                const s1 = s1_count * 4;
                                const s2 = s2_count * 6;
                                const s3 = s3_count * 10;
                                const s4 = s4_count * 14;
                                const s5 = s5_count * 24;
                                const s6 = s6_count * 40;
                                const s7 = s7_count * 70;
                                const adepts = adepts_count * 7;
                                
                                const dances_count = filteredRows.reduce((acc, r) => acc + (r.interval_stats?.[i]?.dances || 0), 0);
                                const dances = playerSum - (s1 + s2 + s3 + s4 + s5 + s6 + s7 + adepts);

                                let tooltipContent = [
                                    s1 > 0 ? `Этап I: +${s1} (${s1_count})` : '',
                                    s2 > 0 ? `Этап II: +${s2} (${s2_count})` : '',
                                    s3 > 0 ? `Этап III: +${s3} (${s3_count})` : '',
                                    s4 > 0 ? `Этап IV: +${s4} (${s4_count})` : '',
                                    s5 > 0 ? `Этап V: +${s5} (${s5_count})` : '',
                                    s6 > 0 ? `Этап VI: +${s6} (${s6_count})` : '',
                                    s7 > 0 ? `Этап VII: +${s7} (${s7_count})` : '',
                                    adepts > 0 ? `Адепты: +${adepts} (${adepts_count})` : '',
                                    dances > 0 ? `Танцы: +${dances} (${dances_count})` : '',
                                    bonus > 0 ? `Бонус гильдии: +${bonus}` : ''
                                ].filter(Boolean);

                                if (tooltipContent.length === 0 && sum > 0) tooltipContent = [`Прочие: +${sum}`];

                                // Add period to the top of tooltip
                                tooltipContent.unshift(formatPeriod(interval.start, interval.end));

                                return (
                                    <div key={i} className="kh-col" style={{ 
                                        justifyContent: 'center', 
                                        display: 'flex', 
                                        alignItems: 'center', 
                                        borderRight: 'none',
                                        boxSizing: 'border-box'
                                    }}>
                                        <GenericTooltip
                                            title="Итого за период"
                                            content={tooltipContent}
                                        >
                                            <span style={{ fontSize: '0.9rem' }}>
                                                {sum.toLocaleString()}
                                            </span>
                                        </GenericTooltip>
                                    </div>
                                );
                            })}

                            {(() => {
                                const playerTotal = filteredRows.reduce((acc, r) => acc + (r.total_valor || 0), 0);
                                const totalValor = playerTotal + totalGuildBonus;

                                const s1_count = filteredRows.reduce((acc, r) => acc + (r.s1 || 0), 0);
                                const s2_count = filteredRows.reduce((acc, r) => acc + (r.s2 || 0), 0);
                                const s3_count = filteredRows.reduce((acc, r) => acc + (r.s3 || 0), 0);
                                const s4_count = filteredRows.reduce((acc, r) => acc + (r.s4 || 0), 0);
                                const s5_count = filteredRows.reduce((acc, r) => acc + (r.s5 || 0), 0);
                                const s6_count = filteredRows.reduce((acc, r) => acc + (r.s6 || 0), 0);
                                const s7_count = filteredRows.reduce((acc, r) => acc + (r.s7 || 0), 0);
                                const adepts_count = filteredRows.reduce((acc, r) => acc + (r.adepts || r.s8 || 0), 0);

                                const s1 = s1_count * 4;
                                const s2 = s2_count * 6;
                                const s3 = s3_count * 10;
                                const s4 = s4_count * 14;
                                const s5 = s5_count * 24;
                                const s6 = s6_count * 40;
                                const s7 = s7_count * 70;
                                const adepts = adepts_count * 7;
                                const dances_count = filteredRows.reduce((acc, r) => acc + (r.dances || 0), 0);
                                const dances = playerTotal - (s1 + s2 + s3 + s4 + s5 + s6 + s7 + adepts);

                                let tooltipContent = [
                                    s1 > 0 ? `Этап I: +${s1} (${s1_count})` : '',
                                    s2 > 0 ? `Этап II: +${s2} (${s2_count})` : '',
                                    s3 > 0 ? `Этап III: +${s3} (${s3_count})` : '',
                                    s4 > 0 ? `Этап IV: +${s4} (${s4_count})` : '',
                                    s5 > 0 ? `Этап V: +${s5} (${s5_count})` : '',
                                    s6 > 0 ? `Этап VI: +${s6} (${s6_count})` : '',
                                    s7 > 0 ? `Этап VII: +${s7} (${s7_count})` : '',
                                    adepts > 0 ? `Адепты: +${adepts} (${adepts_count})` : '',
                                    dances > 0 ? `Танцы: +${dances} (${dances_count})` : '',
                                    totalGuildBonus > 0 ? `Бонус гильдии: +${totalGuildBonus}` : ''
                                ].filter(Boolean);

                                if (tooltipContent.length === 0 && totalValor > 0) {
                                    tooltipContent = [`Прочие: +${totalValor}`];
                                }

                                // Add full period to the top of tooltip
                                if (dateRange.start && dateRange.end) {
                                    tooltipContent.unshift(formatPeriod(dateRange.start, dateRange.end));
                                }

                                return (
                                    <div className="kh-col" style={{ 
                                        justifyContent: 'center', 
                                        display: 'flex', 
                                        alignItems: 'center' 
                                    }}>
                                        <GenericTooltip title="Суммарная доблесть" content={tooltipContent.length > 0 ? tooltipContent : ["Данных нет"]}>
                                            <span style={{ color: 'var(--accent-ruby)' }}>{totalValor.toLocaleString()}</span>
                                        </GenericTooltip>
                                    </div>
                                );
                            })()}
                        </div>
                    )}

                    {!loading && finalDisplayRows.length === 0 && (
                        <div className="text-center p-4 text-muted">No data found for this period.</div>
                    )}

                    </div>
                </div>
            </div>
        </div >
    );
}
