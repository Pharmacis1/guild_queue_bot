"use client";

import React, { useEffect, useState } from 'react';
import { fetchKHTable, KHTableRow } from '@/lib/api';
import ClassIcon from '../shared/ClassIcon';

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
    12: 'Стрелок',
    13: 'Паладин',
    14: 'Странник',
    15: 'Бард',
    16: 'Дух крови',
};

interface KHTableProps {
    onRowClick?: (roleId: number) => void;
}

export default function KHTable({ onRowClick }: KHTableProps) {
    const [loading, setLoading] = useState(true);
    const [rows, setRows] = useState<KHTableRow[]>([]);
    const [dateRange, setDateRange] = useState({ start: '', end: '' });

    // Filters
    const [search, setSearch] = useState('');
    const [entryType, setEntryType] = useState('ALL'); // ALL, NEW, OLD
    const [period, setPeriod] = useState<string>('WEEK'); // TODAY, WEEK, PREV, CUSTOM
    const [myCharsOnly, setMyCharsOnly] = useState(false); // Toggle for "My Characters"
    const [selectedClasses, setSelectedClasses] = useState<number[]>([]); // Empty = all classes
    const [showClassDropdown, setShowClassDropdown] = useState(false);

    const fetchData = (params: any = {}) => {
        setLoading(true);
        fetchKHTable(params)
            .then((data) => {
                setRows(data.rows);
                setDateRange({ start: data.start_date, end: data.end_date });
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
        const matchesMyChars = myCharsOnly ? r.is_mine : true;
        const matchesClass = selectedClasses.length === 0 || selectedClasses.includes(r.class_id);

        return matchesSearch && matchesType && matchesMyChars && matchesClass;
    });

    // Sort by S7 count (descending), then by total_valor
    const sortedRows = [...filteredRows].sort((a, b) => {
        if (b.s7 !== a.s7) return b.s7 - a.s7;
        return b.total_valor - a.total_valor;
    });

    if (loading && rows.length === 0) {
        return <div className="text-center text-silver p-5">Loading Knights Hall...</div>;
    }

    // Helper for stage badges
    const renderStage = (val: number) => {
        if (!val || val <= 0) return null;
        if (val >= 5) return <span className="count-badge count-hot">{val}</span>;
        if (val >= 3) return <span className="count-badge count-silver">{val}</span>;
        return <span className="count-badge count-cold">{val}</span>;
    };

    return (
        <div className="table-container fade-in" style={{ maxWidth: '1400px', margin: '0 auto' }}>
            {/* Control Deck - styled like legacy filter bar */}
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
                {/* Left Group: Class filter, Toggle, Presets, Newcomers */}
                <div style={{ display: 'flex', alignItems: 'center', gap: '12px' }}>
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
                                        <ClassIcon classId={classId} size={18} />
                                        {CLASS_NAMES[classId] || `Class ${classId}`}
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
                                >APPLY</button>
                            </div>
                        )}
                    </div>

                    {/* Toggle My Chars */}
                    <div
                        style={{ display: 'flex', alignItems: 'center', gap: '6px', cursor: 'pointer' }}
                        onClick={() => setMyCharsOnly(!myCharsOnly)}
                        title={myCharsOnly ? 'Showing My Characters' : 'Showing All'}
                    >
                        <span style={{ fontSize: '1rem' }}>👤</span>
                        <div style={{
                            width: '36px',
                            height: '18px',
                            background: myCharsOnly ? 'var(--accent-ruby)' : 'rgba(50, 50, 50, 0.8)',
                            borderRadius: '10px',
                            position: 'relative',
                            border: '1px solid rgba(255, 255, 255, 0.1)',
                            transition: 'background 0.2s'
                        }}>
                            <div style={{
                                width: '14px',
                                height: '14px',
                                background: '#fff',
                                borderRadius: '50%',
                                position: 'absolute',
                                top: '1px',
                                left: myCharsOnly ? '19px' : '2px',
                                transition: 'left 0.2s'
                            }}></div>
                        </div>
                    </div>

                    {/* Preset Buttons: TODAY, WEEK, PREV */}
                    <div className="btn-group" style={{ height: '32px' }}>
                        <button
                            className={`btn btn-sm ${period === 'TODAY' ? 'active' : ''}`}
                            style={{
                                background: period === 'TODAY' ? 'linear-gradient(135deg, var(--accent-ruby) 0%, #8B0000 100%)' : 'transparent',
                                border: '1px solid #444',
                                color: period === 'TODAY' ? '#fff' : '#888',
                                height: '32px',
                                padding: '0 12px',
                                fontSize: '0.75rem',
                                fontWeight: 600
                            }}
                            onClick={() => handleShortcut('TODAY')}
                        >TODAY</button>
                        <button
                            className={`btn btn-sm ${period === 'WEEK' ? 'active' : ''}`}
                            style={{
                                background: period === 'WEEK' ? 'linear-gradient(135deg, var(--accent-ruby) 0%, #8B0000 100%)' : 'transparent',
                                border: '1px solid #444',
                                borderLeft: 'none',
                                color: period === 'WEEK' ? '#fff' : '#888',
                                height: '32px',
                                padding: '0 12px',
                                fontSize: '0.75rem',
                                fontWeight: 600
                            }}
                            onClick={() => handleShortcut('WEEK')}
                        >WEEK</button>
                        <button
                            className={`btn btn-sm ${period === 'PREV' ? 'active' : ''}`}
                            style={{
                                background: period === 'PREV' ? 'linear-gradient(135deg, var(--accent-ruby) 0%, #8B0000 100%)' : 'transparent',
                                border: '1px solid #444',
                                borderLeft: 'none',
                                color: period === 'PREV' ? '#fff' : '#888',
                                height: '32px',
                                padding: '0 12px',
                                fontSize: '0.75rem',
                                fontWeight: 600
                            }}
                            onClick={() => handleShortcut('PREV')}
                        >PREV</button>
                    </div>

                    {/* Newcomers: ALL, NEW, OLD */}
                    <div className="btn-group" style={{ height: '32px' }}>
                        <button
                            className={`btn btn-sm`}
                            style={{
                                background: entryType === 'ALL' ? 'var(--accent-ruby)' : 'transparent',
                                border: '1px solid #444',
                                color: entryType === 'ALL' ? '#fff' : '#888',
                                height: '32px',
                                padding: '0 10px',
                                fontSize: '0.75rem',
                                fontWeight: 600
                            }}
                            onClick={() => setEntryType('ALL')}
                        >ALL</button>
                        <button
                            className={`btn btn-sm`}
                            style={{
                                background: entryType === 'NEW' ? 'var(--accent-ruby)' : 'transparent',
                                border: '1px solid #444',
                                borderLeft: 'none',
                                color: entryType === 'NEW' ? '#fff' : '#888',
                                height: '32px',
                                padding: '0 10px',
                                fontSize: '0.75rem',
                                fontWeight: 600
                            }}
                            onClick={() => setEntryType('NEW')}
                        >NEW</button>
                        <button
                            className={`btn btn-sm`}
                            style={{
                                background: entryType === 'OLD' ? 'var(--accent-ruby)' : 'transparent',
                                border: '1px solid #444',
                                borderLeft: 'none',
                                color: entryType === 'OLD' ? '#fff' : '#888',
                                height: '32px',
                                padding: '0 10px',
                                fontSize: '0.75rem',
                                fontWeight: 600
                            }}
                            onClick={() => setEntryType('OLD')}
                        >OLD</button>
                    </div>

                    {/* Date Inputs */}
                    <div style={{ display: 'flex', alignItems: 'center', gap: '8px' }}>
                        <div style={{
                            display: 'flex',
                            alignItems: 'center',
                            background: 'rgba(0, 0, 0, 0.4)',
                            border: '1px solid rgba(255, 255, 255, 0.1)',
                            borderRadius: '6px',
                            padding: '0 8px',
                            height: '32px'
                        }}>
                            <span style={{ color: '#666', fontSize: '0.7rem', marginRight: '6px' }}>FROM</span>
                            <input
                                type="date"
                                value={dateRange.start}
                                onChange={(e) => setDateRange({ ...dateRange, start: e.target.value })}
                                style={{
                                    background: 'transparent',
                                    border: 'none',
                                    color: '#ccc',
                                    fontSize: '0.8rem',
                                    outline: 'none',
                                    width: '100px'
                                }}
                            />
                        </div>
                        <div style={{
                            display: 'flex',
                            alignItems: 'center',
                            background: 'rgba(0, 0, 0, 0.4)',
                            border: '1px solid rgba(255, 255, 255, 0.1)',
                            borderRadius: '6px',
                            padding: '0 8px',
                            height: '32px'
                        }}>
                            <span style={{ color: '#666', fontSize: '0.7rem', marginRight: '6px' }}>TO</span>
                            <input
                                type="date"
                                value={dateRange.end}
                                onChange={(e) => setDateRange({ ...dateRange, end: e.target.value })}
                                style={{
                                    background: 'transparent',
                                    border: 'none',
                                    color: '#ccc',
                                    fontSize: '0.8rem',
                                    outline: 'none',
                                    width: '100px'
                                }}
                            />
                        </div>
                    </div>
                </div>

                {/* Right Group: Apply Button */}
                <div>
                    <button
                        onClick={handleApply}
                        style={{
                            background: 'linear-gradient(135deg, var(--accent-ruby) 0%, #8B0000 100%)',
                            border: 'none',
                            color: '#fff',
                            height: '32px',
                            padding: '0 20px',
                            borderRadius: '6px',
                            fontSize: '0.8rem',
                            fontWeight: 700,
                            cursor: 'pointer',
                            boxShadow: '0 4px 15px rgba(209, 0, 31, 0.3)'
                        }}
                    >APPLY</button>
                </div>
            </div>

            {/* Table with 10 columns: Participant, I-VII, A, D */}
            <div className="kh-table-body">
                {/* Header inside body so they share same container width */}
                <div className="kh-table-header" style={{
                    display: 'grid',
                    gridTemplateColumns: '2.5fr repeat(7, 1fr) 0.8fr 0.8fr',
                    padding: '10px 16px',
                    gap: '4px',
                    width: '100%',
                    boxSizing: 'border-box',
                    color: '#fff',
                    fontWeight: 700,
                    fontSize: '0.95rem',
                    textTransform: 'uppercase',
                    alignItems: 'center'
                }}>
                    <div className="kh-col kh-participant">
                        <ClassIcon classId={0} size={20} />
                        <span>УЧАСТНИК</span>
                    </div>
                    <div className="kh-col kh-stage">I ↕</div>
                    <div className="kh-col kh-stage">II ↕</div>
                    <div className="kh-col kh-stage">III ↕</div>
                    <div className="kh-col kh-stage">IV ↕</div>
                    <div className="kh-col kh-stage">V ↕</div>
                    <div className="kh-col kh-stage">VI ↕</div>
                    <div className="kh-col kh-stage kh-stage-vii">VII ↕</div>
                    <div className="kh-col kh-stage kh-stage-a">A ↕</div>
                    <div className="kh-col kh-stage kh-stage-d">D ↕</div>
                </div>

                {sortedRows.map((row) => (
                    <div
                        key={row.role_id}
                        className={`kh-row ${row.is_mine ? 'my-row' : ''} ${row.is_afk ? 'afk-row' : ''} ${row.is_newcomer ? 'newcomer-row' : ''}`}
                        onClick={() => onRowClick && onRowClick(row.role_id)}
                        style={{ display: 'grid', gridTemplateColumns: '2.5fr repeat(7, 1fr) 0.8fr 0.8fr', padding: '10px 16px', gap: '4px', width: '100%', boxSizing: 'border-box', cursor: onRowClick ? 'pointer' : 'default' }}
                    >
                        {/* Participant (Icon + Name) */}
                        <div className="kh-col kh-participant">
                            <ClassIcon classId={row.class_id} size={24} />
                            <span className="player-name">{row.name}</span>
                            {row.is_afk && <span className="status-dot afk-dot" title={`AFK: ${row.afk_dates}`}></span>}
                            {row.is_newcomer && <span className="status-dot newcomer-dot" title={`New: ${row.join_days_ago} days`}></span>}
                        </div>

                        {/* Stages I-VII with progression classes */}
                        <div className="kh-col kh-stage stage-early">{renderStage(row.s1)}</div>
                        <div className="kh-col kh-stage stage-early">{renderStage(row.s2)}</div>
                        <div className="kh-col kh-stage stage-mid">{renderStage(row.s3)}</div>
                        <div className="kh-col kh-stage stage-mid">{renderStage(row.s4)}</div>
                        <div className="kh-col kh-stage stage-late">{renderStage(row.s5)}</div>
                        <div className="kh-col kh-stage stage-late">{renderStage(row.s6)}</div>
                        <div className="kh-col kh-stage kh-stage-vii">{renderStage(row.s7)}</div>

                        {/* Adepts & Dances */}
                        <div className="kh-col kh-stage kh-stage-a">
                            {row.adepts > 0 && <span className="count-badge count-hot">{row.adepts}</span>}
                        </div>
                        <div className="kh-col kh-stage kh-stage-d">
                            {row.dances > 0 && <span className="count-badge count-hot">{row.dances}</span>}
                        </div>
                    </div>
                ))}

                {sortedRows.length === 0 && (
                    <div className="text-center p-4 text-muted">No data found for this period.</div>
                )}
            </div>
        </div>
    );
}
