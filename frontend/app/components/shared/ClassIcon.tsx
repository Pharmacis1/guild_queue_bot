import React from 'react';

interface ClassIconProps {
    classId: number;
    className?: string; // Additional CSS classes
    size?: number;
}

const CLASS_NAMES: Record<number, string> = {
    0: 'Воин', 1: 'Маг', 2: 'Шаман', 3: 'Друид', 4: 'Оборотень', 5: 'Убийца',
    6: 'Лучник', 7: 'Жрец', 8: 'Страж', 9: 'Мистик', 10: 'Призрак', 11: 'Жнец',
    12: 'Стрелок', 13: 'Паладин', 14: 'Странник', 15: 'Бард', 16: 'Дух крови'
};

export default function ClassIcon({ classId, className = "", size = 24 }: ClassIconProps) {
    if (classId < 0) {
        // Return placeholder for unknown/invalid class (negative values only)
        return <span style={{ width: size, height: size, display: 'inline-block' }}></span>;
    }
    return (
        <img
            src={`/icons/${classId}.png`}
            alt={`Class ${classId}`}
            width={size}
            height={size}
            className={`class-icon ${className}`}
            title={CLASS_NAMES[classId] || `Class ${classId}`}
            onError={(e) => { e.currentTarget.style.display = 'none'; }}
        />
    );
}
