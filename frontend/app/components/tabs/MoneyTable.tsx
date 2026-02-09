"use client";

import React, { useEffect, useState, useRef } from 'react';
import { fetchMoneyTable, MoneyTableRow } from '@/lib/api';
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
    11: 'Жрец',
    12: 'Стрелок', // Verify ID mapping if needed
    13: 'Паладин',
    14: 'Странник',
    15: 'Бард',
    16: 'Дух крови',
};

interface MoneyTableProps {
    onRowClick?: (roleId: number) => void;
    onObserverClick?: (roleId: number, name: string) => void;
    classes?: Record<string, [string, string, string]>;
}

export default function MoneyTable({ onRowClick, onObserverClick, classes }: MoneyTableProps) {
    const [loading, setLoading] = useState(true);
    const [rows, setRows] = useState<MoneyTableRow[]>([]);
    const [intervals, setIntervals] = useState<{ label: string }[]>([]);
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
        // Merge current state with params overrides
        const queryParams = {
            classes: selectedClasses.length > 0 ? selectedClasses.join(',') : undefined,
            newcomers: entryType === 'NEW' ? 'only' : entryType === 'OLD' ? 'hide' : undefined,
            group_period: groupPeriod,
            group_count: groupCount,
            ...params
        };

        fetchMoneyTable(queryParams)
            .then((data) => {
                setRows(data.rows);
                setIntervals(data.intervals || []);
                setDateRange({ start: data.start_date, end: data.end_date });
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
        const today = new Date();
        let start = new Date();
        let end = new Date();

        if (type === 'TODAY') {
            // start = today
        } else if (type === 'WEEK') {
            const day = today.getDay();
            const diff = today.getDate() - day + (day === 0 ? -6 : 1);
            start.setDate(diff);
        } else if (type === 'PREV') {
            const day = today.getDay();
            const diff = today.getDate() - day + (day === 0 ? -6 : 1) - 7;
            start.setDate(diff);
            end.setDate(diff + 6);
        }

        const fmt = (d: Date) => d.toISOString().split('T')[0];
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

    const getSortIcon = (field: string) => {
        if (sortConfig.field !== field) return '♦';
        return sortConfig.order === 'desc' ? '▼' : '▲';
    };

    const isInitialLoading = loading && rows.length === 0;

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
                padding: '12px 20px',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'space-between',
                gap: '8px',
                position: 'relative',
                zIndex: 100,
                flexWrap: 'wrap' // Allow wrapping if screen is small
            }}>
                {/* Left Group */}
                <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
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
                <div style={{ display: 'flex', alignItems: 'center', gap: '6px' }}>
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
                                    sortedRows.forEach(row => {
                                        if (row.interval_stats && row.interval_stats[i]) {
                                            if (row.interval_stats[i].valor > max) max = row.interval_stats[i].valor;
                                        }
                                    });
                                    return max;
                                });

                                const maxTotalValor = Math.max(...sortedRows.map(row => row.total_valor), 1);

                                return sortedRows.map((row) => {
                                    let rowBg = 'transparent';
                                    let stickyStyle: React.CSSProperties = {
                                        background: 'rgba(5, 5, 5, 1)'
                                    };

                                    if (row.is_newcomer) {
                                        stickyStyle = {
                                            background: '#0d1212',
                                            backgroundImage: 'linear-gradient(to right, rgba(64, 224, 208, 0.15) 0%, rgba(5, 5, 5, 1) 85%)'
                                        };
                                    } else if (row.is_afk) {
                                        stickyStyle = {
                                            background: '#121212',
                                            backgroundImage: 'linear-gradient(to right, rgba(128, 128, 128, 0.15) 0%, rgba(5, 5, 5, 1) 85%)'
                                        };
                                    } else if (row.is_mine) {
                                        stickyStyle = {
                                            background: '#0d120d',
                                            backgroundImage: 'linear-gradient(to right, rgba(50, 205, 50, 0.15) 0%, rgba(5, 5, 5, 1) 85%)'
                                        };
                                    }

                                    return (
                                        <div
                                            key={row.role_id}
                                            className={`kh-row fade-in-smooth kh-row-interactive ${row.is_mine ? 'my-row' : ''} ${row.is_afk ? 'afk-row' : ''} ${row.is_newcomer ? 'newcomer-row' : ''}`}
                                            onClick={() => onRowClick?.(row.role_id)}
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
                                                background: rowBg, // Soft gradient for the rest of the row
                                                borderBottom: '1px solid rgba(255, 255, 255, 0.05)',
                                                alignItems: 'stretch',
                                                cursor: 'pointer'
                                            }}
                                        >
                                            {/* Participant */}
                                            <div className="kh-col kh-participant sticky-col" style={{
                                                ...stickyStyle,
                                                padding: '10px 16px',
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
                                                <ClassIcon classId={row.class_id} size={24} />
                                                <PlayerTooltip
                                                    joinDate={row.join_date}
                                                    joinDaysAgo={row.join_days_ago}
                                                    isAfk={row.is_afk}
                                                    afkDates={row.afk_dates}
                                                >
                                                    <span className="player-name" style={{ marginRight: '4px', whiteSpace: 'nowrap' }}>{row.name}</span>
                                                </PlayerTooltip>
                                                {onObserverClick && (
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
                                            {row.interval_stats?.map((stat, i) => {
                                                const isZero = stat.valor === 0;
                                                let bg = `rgba(139, 0, 0, ${0.3 + (stat.valor / (columnMaxes[i] || 1)) * 0.7})`;
                                                let boxShadow = `0 0 10px rgba(139, 0, 0, ${0.2 + (stat.valor / (columnMaxes[i] || 1)) * 0.4})`;
                                                let border = 'none';
                                                let color = '#fff';

                                                if (stat.is_newcomer_stay) {
                                                    bg = 'rgba(64, 224, 208, 0.2)';
                                                    boxShadow = 'none';
                                                    border = '1px solid rgba(64, 224, 208, 0.3)';
                                                    color = '#fff';
                                                } else if (stat.is_afk_stay) {
                                                    bg = 'rgba(128, 128, 128, 0.2)';
                                                    boxShadow = 'none';
                                                    border = '1px solid rgba(128, 128, 128, 0.3)';
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
                                                                content={stat.valor_details || []}
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
                                            })}

                                            {/* TOTAL SUM */}
                                            <div className="kh-col kh-stage" style={{ justifyContent: 'center' }}>
                                                <span style={{
                                                    background: `rgba(139, 0, 0, ${0.15 + (row.total_valor / maxTotalValor) * 0.45})`,
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
                                                    boxShadow: `0 0 10px rgba(139, 0, 0, ${0.1 + (row.total_valor / maxTotalValor) * 0.3})`
                                                }}>
                                                    {row.total_valor.toLocaleString()}
                                                </span>
                                            </div>
                                        </div>
                                    );
                                });
                            })()
                        )}

                        {!loading && sortedRows.length === 0 && (
                            <div className="text-center p-4 text-muted">No data found for this period.</div>
                        )}
                    </div>
                </div>
            </div>
        </div>
    );
}
