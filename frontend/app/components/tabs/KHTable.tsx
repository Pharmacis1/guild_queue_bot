"use client";

import React, { useEffect, useState } from 'react';
import { fetchKHTable, KHTableRow, UserData } from '@/lib/api';
import ClassIcon from '../shared/ClassIcon';
import PlayerTooltip from '../shared/PlayerTooltip';
import GenericTooltip from '../shared/GenericTooltip';

// Class ID -> Russian Name mapping (from consts.py)
const CLASS_NAMES: Record<number, string> = {
    0: 'Воин',
    1: 'Маг',
    2: 'Шаман',
    3: 'Друид',
    4: 'Оборотень',
    5: 'Убийца',
    6: 'Лучник',
    7: 'Жрец',
    8: 'Страж',
    9: 'Мистик',
    10: 'Призрак',
    11: 'Жнец',
    12: 'Стрелок', // Verify ID mapping
    13: 'Паладин',
    14: 'Странник',
    15: 'Бард',
    16: 'Дух крови',
};

interface KHTableProps {
    onRowClick?: (roleId: number) => void;
    onObserverClick?: (roleId: number, name: string) => void;
    classes?: Record<string, [string, string, string]>;
    currentUser?: UserData | null;
}

export default function KHTable({ onRowClick, onObserverClick, classes, currentUser }: KHTableProps) {
    const [loading, setLoading] = useState(true);
    const [rows, setRows] = useState<KHTableRow[]>([]);
    const [dateRange, setDateRange] = useState({ start: '', end: '' });

    // Filters
    const [search, setSearch] = useState('');
    const [entryType, setEntryType] = useState('ALL'); // ALL, NEW, OLD
    const [afkFilter, setAfkFilter] = useState('ALL'); // ALL, AFK, ONL
    const [period, setPeriod] = useState<string>('WEEK'); // TODAY, WEEK, PREV, CUSTOM
    const [myCharsOnly, setMyCharsOnly] = useState(false); // Toggle for "My Characters"
    const [selectedClasses, setSelectedClasses] = useState<number[]>([]); // Empty = all classes
    const [showClassDropdown, setShowClassDropdown] = useState(false);
    const [sortConfig, setSortConfig] = useState<{ field: string, order: 'asc' | 'desc' }>({ field: 's7', order: 'desc' });
    const [expandedUsers, setExpandedUsers] = useState<Set<number>>(new Set());
    const [initialExpansionDone, setInitialExpansionDone] = useState(false);

    const toggleUserExpansion = (userId: number) => {
        setExpandedUsers(prev => {
            const next = new Set(prev);
            if (next.has(userId)) next.delete(userId);
            else next.add(userId);
            return next;
        });
    };

    const fetchData = (params: any = {}) => {
        setLoading(true);
        fetchKHTable(params)
            .then((data) => {
                setRows(data.rows);
                setDateRange({ start: data.start_date, end: data.end_date });

                // Expand all twins by default on first successful load
                if (!initialExpansionDone && data.rows.length > 0) {
                    const allUserIds = new Set(data.rows.map(r => r.user_id).filter((id): id is number => !!id));
                    setExpandedUsers(allUserIds);
                    setInitialExpansionDone(true);
                }
            })
            .catch((err) => console.error("Failed to fetch KH Table:", err))
            .finally(() => setLoading(false));
    };

    useEffect(() => {
        // Initial fetch
        fetchData();
    }, []);

    const handleApply = () => {
        fetchData({ start: dateRange.start, end: dateRange.end });
        setPeriod('CUSTOM');
    };

    const handleShortcut = (type: string) => {
        setPeriod(type);
        const today = new Date();
        let start = new Date();
        let end = new Date();

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

        return matchesSearch && matchesType && matchesAfk && matchesMyChars && matchesClass;
    });

    const toggleSort = (field: string) => {
        setSortConfig(prev => ({
            field,
            order: prev.field === field && prev.order === 'desc' ? 'asc' : 'desc'
        }));
    };

    // Sort logic
    const sortedRows = [...filteredRows].sort((a: any, b: any) => {
        const field = sortConfig.field;
        const order = sortConfig.order === 'asc' ? 1 : -1;

        if (a[field] !== b[field]) {
            // Sort by value
            if (typeof a[field] === 'string') {
                return order * a[field].localeCompare(b[field]);
            }
            return order * (a[field] - b[field]);
        }
        // Secondary sort: total_valor desc
        return b.total_valor - a.total_valor;
    });

    const finalDisplayRows: KHTableRow[] = [];
    const processedUserIds = new Set<number>();

    for (const row of sortedRows) {
        if (row.user_id) {
            if (processedUserIds.has(row.user_id)) continue;
            processedUserIds.add(row.user_id);

            const groupRows = sortedRows.filter(r => r.user_id === row.user_id);
            // Search for primary character (not an alt)
            const mainRow = groupRows.find(r => !r.is_alt);
            const anchor = mainRow || groupRows[0];
            const others = groupRows.filter(r => r !== anchor).map(r => ({ ...r, _is_child: true }));

            finalDisplayRows.push(anchor);

            if (expandedUsers.has(row.user_id) && others.length > 0) {
                finalDisplayRows.push(...others);
            }
        } else {
            finalDisplayRows.push(row);
        }
    }

    const getSortIcon = (field: string) => {
        if (sortConfig.field !== field) return '♦';
        return sortConfig.order === 'desc' ? '▼' : '▲';
    };

    const ROMAN_MAP: Record<number, string> = {
        1: 'I', 2: 'II', 3: 'III', 4: 'IV', 5: 'V', 6: 'VI', 7: 'VII', 8: 'A', 9: 'D'
    };

    // Helper for stage badges
    const renderStage = (val: number, details?: string[], title?: string) => {
        if (!val || val <= 0) return null;

        const badge = (
            val >= 5 ? <span className="count-badge count-hot">{val}</span> :
                val >= 3 ? <span className="count-badge count-silver">{val}</span> :
                    <span className="count-badge count-cold">{val}</span>
        );

        if (details && details.length > 0) {
            return (
                <GenericTooltip title={title} content={details}>
                    {badge}
                </GenericTooltip>
            );
        }

        return badge;
    };

    const isInitialLoading = loading && rows.length === 0;

    return (
        <div className="table-container fade-in-smooth" style={{ maxWidth: '1200px', margin: '0 auto' }}>
            {/* Control Deck - Standardized UI */}
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
                padding: '12px 20px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                gap: '8px',
                position: 'relative',
                zIndex: 100,
                flexWrap: 'wrap'
            }}>
                {/* Left Group: Class filter, Toggle, Presets, Newcomers */}
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    {/* Class Filter Dropdown */}
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
                            title="Class Filter"
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
                                {/* Get unique classes from data */}
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
                        title={myCharsOnly ? 'Showing My Characters' : 'Showing All'}
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
                                    padding: '4px 10px',
                                    borderRadius: '4px',
                                    fontSize: '0.7rem',
                                    fontWeight: 700,
                                    textTransform: 'uppercase',
                                    cursor: 'pointer',
                                    minWidth: '40px'
                                }}
                            >
                                {s}
                            </button>
                        ))}
                    </div>
                </div>

                {/* Right Group: Date Inputs & Apply */}
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
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

            {/* Darker Table Container as requested */}
            <div style={{
                background: 'rgba(5, 5, 5, 0.85)', // Slightly opaque dark background
                border: '1px solid rgba(255, 255, 255, 0.1)',
                borderRadius: '12px',
                overflow: 'hidden',
                boxShadow: '0 4px 20px rgba(0,0,0,0.6)'
            }}>
                {/* Table Header */}
                <div className="kh-table-header" style={{
                    display: 'grid',
                    gridTemplateColumns: 'minmax(200px, 2.5fr) repeat(9, 1fr)', // Removed Total column
                    paddingLeft: 0,
                    paddingRight: '16px',
                    paddingTop: '12px',
                    paddingBottom: '12px',
                    background: 'rgba(10, 10, 10, 0.95)',
                    borderBottom: '1px solid rgba(255, 255, 255, 0.1)',
                    color: '#aaa',
                    fontWeight: 700,
                    fontSize: '0.85rem',
                    textTransform: 'uppercase',
                    alignItems: 'center',
                    letterSpacing: '0.05em'
                }}>
                    <div
                        className="kh-col"
                        onClick={() => toggleSort('name')}
                        style={{ cursor: 'pointer', display: 'flex', alignItems: 'center', gap: '6px', color: sortConfig.field === 'name' ? '#fff' : '#aaa', paddingLeft: '16px' }}
                    >
                        <ClassIcon classId={0} size={18} />
                        <span>УЧАСТНИК</span>
                        <span style={{ fontSize: '0.7rem', color: 'var(--accent-ruby)' }}>{getSortIcon('name')}</span>
                    </div>

                    {/* Stages 1-9 (Roman for 1-7, then A, D) */}
                    {[1, 2, 3, 4, 5, 6, 7, 8, 9].map(num => (
                        <div
                            key={num}
                            className={`kh-col ${num === 7 ? 'kh-stage-vii' : num === 8 ? 'kh-stage-a' : num === 9 ? 'kh-stage-d' : ''}`}
                            onClick={() => toggleSort(`s${num}`)}
                            style={{ cursor: 'pointer', textAlign: 'center', color: sortConfig.field === `s${num}` ? '#fff' : '#888' }}
                        >
                            {ROMAN_MAP[num] || num}
                        </div>
                    ))}
                </div>

                {/* Table Body */}
                <div className={loading && rows.length > 0 ? "loading-blur" : ""}>
                    {isInitialLoading ? (
                        /* Ghost Rows (No inner squares) */
                        Array.from({ length: 15 }).map((_, i) => (
                            <div key={i} className="kh-row skeleton-row" style={{
                                display: 'grid',
                                gridTemplateColumns: 'minmax(200px, 2.5fr) repeat(9, 1fr)',
                                paddingRight: '16px',
                                borderBottom: '1px solid rgba(255, 255, 255, 0.05)',
                                minHeight: '44px',
                                alignItems: 'center'
                            }}>
                                <div className="kh-col kh-participant" style={{ gap: '10px', paddingLeft: '16px' }}>
                                    {/* Empty shimmering row */}
                                </div>
                                {Array.from({ length: 9 }).map((_, j) => (
                                    <div key={j} className="kh-col"></div>
                                ))}
                            </div>
                        ))
                    ) : (
                        finalDisplayRows.map(row => {
                            let rowBg = 'transparent';
                            if (row.is_newcomer) rowBg = 'linear-gradient(to right, rgba(64, 224, 208, 0.3) 0%, transparent 100%)';
                            else if (row.is_afk) rowBg = 'linear-gradient(to right, rgba(192, 192, 192, 0.3) 0%, transparent 100%)';
                            else if (row.is_mine) rowBg = 'linear-gradient(to right, rgba(50, 205, 50, 0.25) 0%, transparent 100%)';

                            const isExpanded = row.user_id ? expandedUsers.has(row.user_id) : false;
                            const hasTwins = row.user_id ? sortedRows.filter(r => r.user_id === row.user_id).length > 1 : false;
                            const isGroupAnchor = row.user_id && !row.is_alt && hasTwins;
                            const isChild = !!(row as any)._is_child;
                            const participantAllocatedPadding = isChild ? '64px' : '16px';

                            return (
                                <div
                                    key={row.role_id}
                                    className={`kh-row fade-in-smooth ${row.is_mine ? 'my-row' : ''} ${row.is_afk ? 'afk-row' : ''} ${row.is_newcomer ? 'newcomer-row' : ''}`}
                                    onMouseOver={(e) => {
                                        if (row.is_newcomer) e.currentTarget.style.background = 'rgba(64, 224, 208, 0.05)';
                                        else if (row.is_afk) e.currentTarget.style.background = 'rgba(192, 192, 192, 0.1)';
                                        else if (!row.is_mine) e.currentTarget.style.background = 'rgba(255, 255, 255, 0.03)';
                                    }}
                                    onMouseOut={(e) => {
                                        e.currentTarget.style.background = 'transparent';
                                    }}
                                    // onClick={() => onRowClick?.(row.role_id)} // Removed
                                    style={{
                                        display: 'grid',
                                        gridTemplateColumns: 'minmax(200px, 2.5fr) repeat(9, 1fr)',
                                        paddingLeft: 0,
                                        paddingRight: '16px',
                                        borderBottom: '1px solid rgba(255, 255, 255, 0.08)',
                                        alignItems: 'stretch',
                                        transition: 'background 0.2s',
                                        background: 'transparent',
                                        minHeight: '44px',
                                        cursor: 'default'
                                    }}
                                >
                                    <div className="kh-col kh-participant" style={{
                                        display: 'flex',
                                        alignItems: 'center',
                                        gap: '10px',
                                        background: rowBg,
                                        padding: '10px 16px 10px 16px',
                                        height: '100%',
                                        boxSizing: 'border-box',
                                        position: 'relative',
                                        paddingLeft: participantAllocatedPadding
                                    }}>
                                        {/* CP Neon Strip */}
                                        {row.cp_color && (
                                            <div style={{
                                                position: 'absolute',
                                                left: 0,
                                                top: 0,
                                                bottom: 0,
                                                width: '4px',
                                                background: row.cp_color,
                                                boxShadow: `0 0 10px ${row.cp_color}`
                                            }} />
                                        )}



                                        <ClassIcon classId={row.class_id} size={24} />
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
                                                    cursor: currentUser?.is_master ? 'pointer' : 'default'
                                                }}
                                                onClick={(e) => {
                                                    if (currentUser?.is_master && onRowClick) {
                                                        e.stopPropagation();
                                                        onRowClick(row.role_id);
                                                    }
                                                }}
                                            >
                                                {row.name}
                                                {hasTwins && !isChild && (
                                                    <span
                                                        onClick={(e) => {
                                                            e.stopPropagation();
                                                            if (row.user_id) toggleUserExpansion(row.user_id);
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
                                            </span>
                                        </PlayerTooltip>
                                        {onObserverClick && currentUser?.is_master && (
                                            <button
                                                onClick={(e) => {
                                                    e.stopPropagation();
                                                    onObserverClick(row.role_id, row.name);
                                                }}
                                                className="btn-observer-spider"
                                                style={{
                                                    background: 'none', border: 'none', cursor: 'pointer',
                                                    fontSize: '0.9rem', opacity: 0.15, padding: 0,
                                                    lineHeight: 1
                                                }}
                                            >🕷️</button>
                                        )}
                                    </div>

                                    {
                                        [
                                            { val: row.s1, det: row.s1_details, t: 'I' },
                                            { val: row.s2, det: row.s2_details, t: 'II' },
                                            { val: row.s3, det: row.s3_details, t: 'III' },
                                            { val: row.s4, det: row.s4_details, t: 'IV' },
                                            { val: row.s5, det: row.s5_details, t: 'V' },
                                            { val: row.s6, det: row.s6_details, t: 'VI' },
                                            { val: row.s7, det: row.s7_details, t: 'VII' },
                                            { val: row.adepts || row.s8, det: [], t: 'A' },
                                            { val: row.dances || row.s9, det: [], t: 'D' }
                                        ].map((item, idx) => {
                                            let stageClass = "kh-col";
                                            if (idx < 2) stageClass += " stage-early";
                                            else if (idx < 4) stageClass += " stage-mid";
                                            else if (idx < 6) stageClass += " stage-late";
                                            else if (idx === 6) stageClass += " kh-stage-vii";
                                            else if (idx === 7) stageClass += " kh-stage-a";
                                            else if (idx === 8) stageClass += " kh-stage-d";

                                            return (
                                                <div key={idx} className={stageClass} style={{ textAlign: 'center', display: 'flex', alignItems: 'center', justifyContent: 'center' }}>
                                                    {renderStage(item.val, item.det, item.t ? `Этап ${item.t}` : undefined)}
                                                </div>
                                            );
                                        })
                                    }
                                </div>
                            )
                        })
                    )}

                    {!loading && sortedRows.length === 0 && (
                        <div className="text-center p-5 text-muted">No data found.</div>
                    )}
                </div>
            </div>
        </div >
    );
}
