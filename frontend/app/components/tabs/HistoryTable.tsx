"use client";

import React, { useEffect, useState } from 'react';
import { fetchHistoryTable, HistoryRow } from '@/lib/api';
import ClassIcon from '../shared/ClassIcon';

export default function HistoryTable() {
    const [loading, setLoading] = useState(true);
    const [rows, setRows] = useState<HistoryRow[]>([]);

    useEffect(() => {
        fetchHistoryTable()
            .then(setRows)
            .catch((err) => console.error("Failed to fetch History:", err))
            .finally(() => setLoading(false));
    }, []);

    if (loading) return <div className="text-center text-silver p-5">Loading History...</div>;

    return (
        <div className="table-container fade-in">
            <div className="overflow-x-auto">
                <table className="spider-table w-full">
                    <thead>
                        <tr>
                            <th style={{ width: '60px' }}>Иконка</th>
                            <th>Действие / Описание</th>
                            <th className="text-right">Дата</th>
                        </tr>
                    </thead>
                    <tbody>
                        {rows.map((row, idx) => (
                            <tr key={idx} className={row.is_mine ? 'my-row' : ''}>
                                <td className="text-center">
                                    {row.class_id > 0 && <ClassIcon classId={row.class_id} />}
                                </td>
                                <td>
                                    <div className="history-desc">
                                        {row.name && <span className="h-name">{row.name}</span>}
                                        {row.desc}
                                        {row.item_name && <span className="h-item"> [{row.item_name}]</span>}
                                    </div>
                                </td>
                                <td className="text-right text-muted small">
                                    {row.date.split(' ')[0]} {/* Show Date Only */}
                                    <br />
                                    {row.date.split(' ')[1]} {/* Show Time */}
                                </td>
                            </tr>
                        ))}
                        {rows.length === 0 && (
                            <tr>
                                <td colSpan={3} className="text-center text-muted p-4">No history events found.</td>
                            </tr>
                        )}
                    </tbody>
                </table>
            </div>
        </div>
    );
}
