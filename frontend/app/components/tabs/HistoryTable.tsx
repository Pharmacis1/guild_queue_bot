"use client";

import React, { useEffect, useState, useMemo } from 'react';
import { fetchHistoryTable, HistoryRow, UserData } from '@/lib/api';
import ClassIcon from '../shared/ClassIcon';
import PlayerTooltip from '../shared/PlayerTooltip';

interface HistoryTableProps {
    onRowClick?: (roleId: number) => void;
    onObserverClick?: (roleId: number, name: string) => void;
    classes?: Record<string, [string, string, string]>;
    currentUser?: UserData | null;
}

const getActionStyle = (desc: string) => {
    // "Получил", "Created", "Found" -> Loot (Yellow/Gold)
    if (desc.includes('Получил') || desc.includes('Created') || desc.includes('Found')) {
        return {
            bg: 'rgba(255, 215, 0, 0.1)',
            border: '1px solid rgba(255, 215, 0, 0.3)',
            color: '#ffd700',
            icon: '💰'
        };
    }
    // "Вклад" -> Contribution (Red)
    if (desc.includes('Вклад')) {
        return {
            bg: 'rgba(139, 0, 0, 0.2)', // Dark Red tint
            border: '1px solid rgba(139, 0, 0, 0.4)',
            color: '#ff6666', // Brighter Red text
            icon: '⚔️'
        };
    }
    // "Вступил" -> Join (Green/Cyan)
    if (desc.includes('Вступил')) {
        return {
            bg: 'rgba(50, 205, 50, 0.1)',
            border: '1px solid rgba(50, 205, 50, 0.3)',
            color: '#32cd32',
            icon: '👋'
        };
    }
    // "Вышел", "Kicked" -> Leave (Dark Gray/Red)
    if (desc.includes('Вышел') || desc.includes('Kicked') || desc.includes('Left')) {
        return {
            bg: 'rgba(128, 128, 128, 0.1)',
            border: '1px solid rgba(128, 128, 128, 0.3)',
            color: '#aaa',
            icon: '🚪'
        };
    }

    // Default
    return {
        bg: 'rgba(255, 255, 255, 0.05)',
        border: '1px solid rgba(255, 255, 255, 0.1)',
        color: '#ccc',
        icon: '📝'
    };
};

const formatItemName = (name: string) => {
    // Remove "ID 12345 " prefix and brackets
    return name.replace(/ID \d+\s*/g, '').replace(/[\[\]]/g, '').trim();
};

const formatDescription = (desc: string) => {
    // [FIX] Keep IDs if present, as they provide useful info when nicknames are missing
    return desc.trim();
};

const EVENT_LABELS: Record<string, string> = {
    'ROSTER': 'СОСТАВ',
    'ALL': 'ВСЕ',
    'LOOT': 'ЛУТ',
    'CONTR': 'ВКЛАД'
};

export default function HistoryTable({ onRowClick, onObserverClick, classes, currentUser }: HistoryTableProps) {
    const [loading, setLoading] = useState(true);
    const [allRows, setAllRows] = useState<HistoryRow[]>([]);

    // Filters
    const [selectedClasses, setSelectedClasses] = useState<number[]>([]);
    const [showClassDropdown, setShowClassDropdown] = useState(false);
    const [myCharsOnly, setMyCharsOnly] = useState(false);

    const [dateRange, setDateRange] = useState('week'); // 'today', 'week', 'prev', 'custom'
    const [customFrom, setCustomFrom] = useState('');
    const [customTo, setCustomTo] = useState('');

    const [eventType, setEventType] = useState('ROSTER'); // [FIX] Default to ROSTER
    const [showEventDropdown, setShowEventDropdown] = useState(false);

    // Helper to format date as YYYY-MM-DD
    const formatDate = (date: Date) => {
        const y = date.getFullYear();
        const m = String(date.getMonth() + 1).padStart(2, '0');
        const d = String(date.getDate()).padStart(2, '0');
        return `${y}-${m}-${d}`;
    };

    useEffect(() => {
        setLoading(true);
        const now = new Date();
        const startDay = new Date(now.getFullYear(), now.getMonth(), now.getDate());
        let endDay = new Date(startDay);

        const params: any = {};

        if (dateRange === 'today') {
            params.start = formatDate(startDay);
        } else if (dateRange === 'week') {
            startDay.setDate(startDay.getDate() - 7);
            params.start = formatDate(startDay);
        } else if (dateRange === 'prev') {
            endDay.setDate(endDay.getDate() - 7);
            startDay.setDate(startDay.getDate() - 14);
            params.start = formatDate(startDay);
            params.end = formatDate(endDay);
        } else if (dateRange === 'custom' && customFrom && customTo) {
            params.start = customFrom;
            params.end = customTo;
        }

        // Add event types mapping for API
        if (eventType !== 'ALL') {
            if (eventType === 'LOOT') params.types = 'items';
            if (eventType === 'CONTR') params.types = 'valor,gold';
            if (eventType === 'ROSTER') params.types = 'roster';
        }

        fetchHistoryTable(params)
            .then(setAllRows)
            .catch((err) => console.error("Failed to fetch History:", err))
            .finally(() => setLoading(false));
    }, [dateRange, customFrom, customTo, eventType]);

    // Helper to parse date string "YYYY-MM-DD HH:MM:SS"
    const parseDate = (dateStr: string) => {
        return new Date(dateStr.replace(' ', 'T'));
    };

    const filteredRows = useMemo(() => {
        let rows = [...allRows];

        // 1. Class Filter
        if (selectedClasses.length > 0) {
            rows = rows.filter(r => selectedClasses.includes(r.class_id));
        }

        // 2. My Chars
        if (myCharsOnly) {
            rows = rows.filter(r => r.is_mine);
        }

        // Date and Type filtering now handled by API
        // Any additional client-side filtering can remain here (Class, MyChars)

        return rows;
    }, [allRows, selectedClasses, myCharsOnly]);

    const isInitialLoading = loading && allRows.length === 0;

    const uniqueClasses = Array.from(new Set(allRows.map(r => r.class_id))).filter(id => id >= 0).sort((a, b) => a - b);

    return (
        <div className="table-container fade-in-smooth" style={{ maxWidth: '1000px', margin: '0 auto', paddingBottom: '40px' }}>

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
                padding: '12px 20px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                gap: '12px',
                position: 'relative',
                zIndex: 100
            }}>
                {/* Left Group: Class & MyChars */}
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>

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
                                        onClick={() => setSelectedClasses(uniqueClasses)}
                                    >SELECT ALL</button>
                                    <button
                                        className="btn btn-xs"
                                        style={{ flex: 1, background: 'transparent', border: '1px solid #555', color: '#aaa', fontSize: '0.7rem' }}
                                        onClick={() => setSelectedClasses([])}
                                    >CLEAR</button>
                                </div>
                                {uniqueClasses.map(classId => (
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
                                            onChange={(e) => {
                                                if (e.target.checked) setSelectedClasses([...selectedClasses, classId]);
                                                else setSelectedClasses(selectedClasses.filter(id => id !== classId));
                                            }}
                                        />
                                        <ClassIcon classId={classId} size={16} />
                                        <span>{classes?.[classId.toString()]?.[0] || `Class ${classId}`}</span>
                                    </label>
                                ))}
                            </div>
                        )}
                    </div>

                    {/* My Chars Toggle */}
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

                    {/* Date Presets */}
                    <div className="btn-group" style={{ display: 'flex', background: '#111', borderRadius: '6px', padding: '2px' }}>
                        {['today', 'week', 'prev'].map(r => (
                            <button
                                key={r}
                                onClick={() => setDateRange(r)}
                                style={{
                                    background: dateRange === r ? 'var(--accent-ruby)' : 'transparent',
                                    color: dateRange === r ? '#fff' : '#666',
                                    border: 'none',
                                    padding: '4px 12px',
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

                    {/* Event Type Filter */}
                    <div style={{ position: 'relative' }}>
                        <button
                            className="btn btn-sm"
                            style={{
                                background: 'transparent',
                                border: '1px solid #444',
                                color: '#ccc',
                                height: '32px',
                                padding: '0 12px',
                                borderRadius: '6px',
                                minWidth: '100px',
                                display: 'flex', justifyContent: 'space-between', alignItems: 'center'
                            }}
                            onClick={() => setShowEventDropdown(!showEventDropdown)}
                        >
                            {EVENT_LABELS[eventType] || eventType} <span style={{ fontSize: '0.7rem' }}>▼</span>
                        </button>
                        {showEventDropdown && (
                            <div style={{
                                position: 'absolute', top: '36px', left: 0,
                                background: '#1a1a1a', border: '1px solid #444', borderRadius: '6px',
                                padding: '4px', zIndex: 1000, minWidth: '120px'
                            }}>
                                {Object.keys(EVENT_LABELS).map(et => (
                                    <div
                                        key={et}
                                        onClick={() => { setEventType(et); setShowEventDropdown(false); }}
                                        style={{
                                            padding: '6px 12px', cursor: 'pointer',
                                            color: eventType === et ? '#fff' : '#888',
                                            background: eventType === et ? 'rgba(255,255,255,0.1)' : 'transparent',
                                            fontSize: '0.8rem'
                                        }}
                                    >
                                        {EVENT_LABELS[et]}
                                    </div>
                                ))}
                            </div>
                        )}
                    </div>

                </div>

                {/* Right Group: Custom Date */}
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                    <div style={{ display: 'flex', alignItems: 'center', background: '#111', borderRadius: '6px', padding: '0 8px', border: '1px solid #333' }}>
                        <span style={{ fontSize: '0.7rem', color: '#666', marginRight: '6px', textTransform: 'uppercase' }}>FROM</span>
                        <input
                            type="date"
                            value={customFrom}
                            onChange={(e) => { setCustomFrom(e.target.value); setDateRange('custom'); }}
                            style={{ background: 'transparent', border: 'none', color: '#fff', fontSize: '0.8rem', padding: '4px 0', outline: 'none' }}
                        />
                    </div>
                    <div style={{ display: 'flex', alignItems: 'center', background: '#111', borderRadius: '6px', padding: '0 8px', border: '1px solid #333' }}>
                        <span style={{ fontSize: '0.7rem', color: '#666', marginRight: '6px', textTransform: 'uppercase' }}>TO</span>
                        <input
                            type="date"
                            value={customTo}
                            onChange={(e) => { setCustomTo(e.target.value); setDateRange('custom'); }}
                            style={{ background: 'transparent', border: 'none', color: '#fff', fontSize: '0.8rem', padding: '4px 0', outline: 'none' }}
                        />
                    </div>
                </div>
            </div>

            <div style={{ display: 'flex', flexDirection: 'column', gap: '8px' }} className={loading && allRows.length > 0 ? "loading-blur" : ""}>
                {isInitialLoading ? (
                    /* Shimmering Ghost Rows */
                    Array.from({ length: 12 }).map((_, i) => (
                        <div key={i} className="history-row-card skeleton-row" style={{
                            background: 'rgba(10, 10, 10, 0.2)',
                            padding: '16px 24px',
                            minHeight: '70px',
                            borderRadius: '4px'
                        }}>
                        </div>
                    ))
                ) : (
                    filteredRows.map((row, idx) => {
                        const style = getActionStyle(row.desc);
                        const [date, time] = row.date.split(' ');

                        return (
                            <div key={idx}
                                className="history-row-card fade-in-smooth"
                                style={{
                                    display: 'flex',
                                    alignItems: 'center',
                                    background: 'rgba(25, 25, 25, 0.6)',
                                    borderBottom: '1px solid rgba(255, 255, 255, 0.05)',
                                    padding: '16px 24px',
                                    borderRadius: '4px',
                                    transition: 'background 0.2s',
                                    cursor: 'default' // Changed from pointer
                                }}
                                onMouseOver={(e) => e.currentTarget.style.background = 'rgba(20, 20, 20, 0.8)'}
                                onMouseOut={(e) => e.currentTarget.style.background = 'rgba(10, 10, 10, 0.4)'}
                            // onClick={() => onRowClick?.(row.role_id)} // Removed
                            >
                                {/* Date Column */}
                                <div style={{ minWidth: '100px', display: 'flex', flexDirection: 'column', marginRight: '32px' }}>
                                    <span style={{ color: '#ccc', fontWeight: 600, fontSize: '0.9rem', marginBottom: '4px' }}>{date}</span>
                                    <span style={{ color: '#666', fontSize: '0.75rem', fontFamily: 'monospace' }}>{time}</span>
                                </div>

                                {/* Player Column */}
                                <div className="kh-participant" style={{ minWidth: '200px', display: 'flex', alignItems: 'center', marginRight: '32px', paddingLeft: 0 }}>
                                    <div style={{ marginRight: '12px', display: 'flex', alignItems: 'center' }}>
                                        <ClassIcon classId={row.class_id} size={28} />
                                    </div>
                                    <PlayerTooltip
                                        joinDate={row.join_date}
                                        joinDaysAgo={row.join_days_ago}
                                        isAfk={row.is_afk}
                                        afkDates={row.afk_dates}
                                    >
                                        <span
                                            className="player-name"
                                            style={{
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
                                            {row.name || 'Unknown'}
                                        </span>
                                    </PlayerTooltip>
                                    {onObserverClick && row.role_id && currentUser?.is_master && (
                                        <button
                                            onClick={(e) => {
                                                e.stopPropagation();
                                                if (row.name) onObserverClick(row.role_id, row.name);
                                            }}
                                            className="btn-observer-spider"
                                            title="View Equipment"
                                            style={{
                                                background: 'none',
                                                border: 'none',
                                                cursor: 'pointer',
                                                fontSize: '0.9rem',
                                                marginLeft: '10px',
                                                opacity: 0.1,
                                                padding: 0,
                                                lineHeight: 1,
                                                transition: 'opacity 0.2s',
                                                filter: 'grayscale(100%) brightness(0.7)'
                                            }}
                                            onMouseOver={(e) => {
                                                e.currentTarget.style.opacity = '0.8';
                                                e.currentTarget.style.filter = 'none';
                                            }}
                                            onMouseOut={(e) => {
                                                e.currentTarget.style.opacity = '0.1';
                                                e.currentTarget.style.filter = 'grayscale(100%) brightness(0.7)';
                                            }}
                                        >
                                            🕷️
                                        </button>
                                    )}
                                </div>

                                {/* Action Badge */}
                                <div style={{ flex: 1 }}>
                                    <div style={{
                                        display: 'inline-flex',
                                        alignItems: 'center',
                                        padding: '8px 16px',
                                        background: style.bg,
                                        border: style.border,
                                        color: style.color,
                                        borderRadius: '6px',
                                        fontSize: '0.9rem',
                                        fontWeight: 500,
                                        boxShadow: '0 2px 5px rgba(0,0,0,0.2)'
                                    }}>
                                        <span style={{ marginRight: '10px', fontSize: '1.1rem' }}>{style.icon}</span>
                                        <span>
                                            {formatDescription(row.desc)}
                                            {row.item_name && <span style={{ opacity: 0.85, marginLeft: '6px', fontWeight: 600 }}>[{formatItemName(row.item_name)}]</span>}
                                        </span>
                                    </div>
                                </div>
                            </div>
                        );
                    })
                )}

                {!loading && filteredRows.length === 0 && (
                    <div className="text-center text-muted p-5" style={{ background: 'rgba(10,10,10,0.4)', borderRadius: '4px' }}>
                        No history events found for selected filters.
                    </div>
                )}
            </div>
        </div>
    );
}
