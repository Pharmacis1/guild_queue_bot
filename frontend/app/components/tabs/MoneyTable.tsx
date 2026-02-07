"use client";

import React, { useEffect, useState } from 'react';
import { fetchMoneyTable, MoneyTableRow } from '@/lib/api';
import ClassIcon from '../shared/ClassIcon';

export default function MoneyTable() {
    const [loading, setLoading] = useState(true);
    const [rows, setRows] = useState<MoneyTableRow[]>([]);
    const [intervals, setIntervals] = useState<{ label: string }[]>([]);
    const [meta, setMeta] = useState({ start: '', end: '', group: 'day' });

    useEffect(() => {
        fetchMoneyTable()
            .then((data) => {
                setRows(data.rows);
                setIntervals(data.intervals || []);
                setMeta({
                    start: data.start_date,
                    end: data.end_date,
                    group: data.group_period || 'day'
                });
            })
            .catch((err) => console.error("Failed to fetch Money Table:", err))
            .finally(() => setLoading(false));
    }, []);

    if (loading) return <div className="text-center text-silver p-5">Loading Financials...</div>;

    return (
        <div className="table-container fade-in">
            <div className="text-center mb-3">
                <span className="badge-spider">Data from {meta.start} to {meta.end}</span>
            </div>

            <div className="overflow-x-auto">
                <table className="spider-table w-full">
                    <thead>
                        <tr>
                            <th className="sticky-col">Никнейм</th>
                            <th>Класс</th>
                            <th>Всего</th>
                            {intervals.map((interval: any, i) => (
                                <th key={i} className="date-header">{interval.label}</th>
                            ))}
                        </tr>
                    </thead>
                    <tbody>
                        {rows.map((row) => (
                            <tr key={row.role_id} className={row.is_mine ? 'my-row' : ''}>
                                <td className="sticky-col name-col">
                                    {row.name}
                                    {row.is_newcomer && <span className="dot-newcomer" title="Newcomer">●</span>}
                                </td>
                                <td className="text-center"><ClassIcon classId={row.class_id} /></td>
                                <td className="text-gold font-bold text-right pr-4">{row.total_gold.toLocaleString()}</td>

                                {/* Interval Columns */}
                                {row.interval_stats?.map((stat, i) => {
                                    // Determine cell styling based on status
                                    let cellClass = "";
                                    if (stat.is_pre_join) cellClass = "cell-pre-join";
                                    else if (stat.is_newcomer_stay) cellClass = "cell-newcomer";
                                    else if (stat.is_afk_stay) cellClass = "cell-afk";

                                    return (
                                        <td key={i} className={`text-right ${cellClass}`} title={`Gold: ${stat.gold}`}>
                                            {stat.gold > 0 ? stat.gold.toLocaleString() : '-'}
                                        </td>
                                    );
                                })}
                            </tr>
                        ))}
                    </tbody>
                </table>
            </div>
        </div>
    );
}
