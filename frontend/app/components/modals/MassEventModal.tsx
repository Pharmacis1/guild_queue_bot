"use client";

import React, { useState } from 'react';
import { addEventBulk } from '@/lib/api';

interface MassEventModalProps {
    isOpen: boolean;
    onClose: () => void;
    onSuccess: () => void;
    selectedRoleIds: number[];
}

export default function MassEventModal({ isOpen, onClose, onSuccess, selectedRoleIds }: MassEventModalProps) {
    const [date, setDate] = useState('');
    const [value, setValue] = useState('');
    const [description, setDescription] = useState('');
    const [loading, setLoading] = useState(false);
    const [error, setError] = useState<string | null>(null);

    // Set default date to current local date/time (without seconds for input)
    React.useEffect(() => {
        if (isOpen) {
            const now = new Date();
            const year = now.getFullYear();
            const month = String(now.getMonth() + 1).padStart(2, '0');
            const day = String(now.getDate()).padStart(2, '0');
            const hours = String(now.getHours()).padStart(2, '0');
            const minutes = String(now.getMinutes()).padStart(2, '0');
            setDate(`${year}-${month}-${day}T${hours}:${minutes}`);
            setValue('');
            setDescription('');
            setError(null);
        }
    }, [isOpen]);

    if (!isOpen) return null;

    const handleSubmit = async (e: React.FormEvent) => {
        e.preventDefault();
        setError(null);

        if (!date || !value) {
            setError("Пожалуйста, заполните дату и значение (кол-во Доблести)");
            return;
        }

        if (selectedRoleIds.length === 0) {
            setError("Не выбрано ни одного игрока");
            return;
        }

        setLoading(true);
        try {
            const res = await addEventBulk({
                role_ids: selectedRoleIds,
                date,
                value: parseInt(value, 10),
                description
            });

            if (res.status === 'error') {
                setError(res.message);
            } else {
                onSuccess(); // Close and refresh
            }
        } catch (err: any) {
            setError(err.message || "Произошла ошибка");
        } finally {
            setLoading(false);
        }
    };

    return (
        <div className="modal-backdrop" onClick={onClose} style={{ zIndex: 9999 }}>
            <div className="modal-content" onClick={e => e.stopPropagation()} style={{ maxWidth: '400px', width: '90%' }}>
                <div className="modal-header">
                    <h3 style={{ margin: 0, color: 'var(--accent-ruby)' }}>Массовое начисление</h3>
                    <button onClick={onClose} className="btn-close">×</button>
                </div>

                <div style={{ padding: '0 20px', fontSize: '0.85rem', color: '#888', marginBottom: '10px' }}>
                    Выбрано игроков: {selectedRoleIds.length}
                </div>

                <form onSubmit={handleSubmit} style={{ display: 'flex', flexDirection: 'column', gap: '16px', padding: '10px 20px 20px' }}>

                    <div className="form-group">
                        <label>Дата и Время (МСК):</label>
                        <input
                            type="datetime-local"
                            value={date}
                            onChange={(e) => setDate(e.target.value)}
                            className="form-control"
                            required
                        />
                    </div>

                    <div className="form-group">
                        <label>Кол-во Доблести:</label>
                        <input
                            type="number"
                            value={value}
                            onChange={(e) => setValue(e.target.value)}
                            className="form-control"
                            required
                        />
                    </div>

                    <div className="form-group">
                        <label>Описание (опционально):</label>
                        <input
                            type="text"
                            value={description}
                            onChange={(e) => setDescription(e.target.value)}
                            className="form-control"
                            placeholder="Например: За победу в турнире"
                        />
                    </div>

                    {error && (
                        <div style={{ color: '#ff4d4d', fontSize: '0.85rem', background: 'rgba(255,0,0,0.1)', padding: '8px', borderRadius: '4px' }}>
                            {error}
                        </div>
                    )}

                    <div style={{ display: 'flex', justifyContent: 'flex-end', gap: '10px', marginTop: '10px' }}>
                        <button type="button" onClick={onClose} className="btn" style={{ background: '#333', color: '#fff' }}>Отмена</button>
                        <button type="submit" className="btn btn-primary" disabled={loading} style={{ minWidth: '100px' }}>
                            {loading ? 'Идет запись...' : 'Начислить'}
                        </button>
                    </div>
                </form>
            </div>
        </div>
    );
}
