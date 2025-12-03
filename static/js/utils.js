// static/js/utils.js

// Базовые наборы для фоллбэка
const EMOJI_POOLS = {
    'Biome': ['🌲', '🌵', '🏔️', '🌊', '🌴', '🌑', '❄️', '🌋', '🍄', '🌾'],
    'Location': ['🛖', '🏰', '🗿', '⛺', '🏛️', '🏚️', '🌲', '🕳️', '🏠', '🗼'],
    'Faction': ['⚔️', '🛡️', '👑', '🧙', '🧝', '👁️', '🏹', '⚒️'],
    'Bosses': ['💀','🐉'],
    'Resource': ['🪵', '💎', '🍖', '💧', '🌾', '⛏️', '💊', '📜'],
    'default': ['❓', '✨', '🎲', '🌀']
};

/**
 * Генерирует хеш-число из строки. 
 * Используется для того, чтобы для одного ID всегда возвращался один и тот же цвет/эмодзи.
 */
function hashCode(str) {
    let hash = 0;
    if (!str || str.length === 0) return hash;
    for (let i = 0; i < str.length; i++) {
        const char = str.charCodeAt(i);
        hash = ((hash << 5) - hash) + char;
        hash |= 0; // Convert to 32bit integer
    }
    return Math.abs(hash);
}

export const utils = {
    /**
     * Возвращает иконку для сущности.
     * Приоритет: 
     * 1. icon из данных (если задан в шаблоне)
     * 2. Детерминированный выбор из пула по типу сущности
     */
    getIcon(entity) {
        // 1. Если пришло с бэкенда (например, добавили поле в шаблон)
        if (entity.data && entity.data.icon) return entity.data.icon;
        if (entity.icon) return entity.icon; // Если поле на верхнем уровне
        
        // 2. Иначе генерируем на основе ID
        const type = entity.type || 'default';
        const pool = EMOJI_POOLS[type] || EMOJI_POOLS['default'];
        
        // Используем definition_id (шаблон), чтобы все "Леса" выглядели одинаково,
        // ИЛИ entity.id, чтобы каждый лес был уникальным. 
        // Логичнее брать definition_id (biome_forest -> всегда 🌲)
        const seed = entity.definition_id || entity.id || 'unknown';
        const index = hashCode(seed) % pool.length;
        
        return pool[index];
    },

    /**
     * Генерирует пастельный цвет на основе строки (ID)
     */
    getColor(str, opacity = 1.0) {
        const hash = hashCode(str);
        // Генерируем HSL для приятных цветов
        const h = hash % 360;
        const s = 60 + (hash % 20); // 60-80% saturation
        const l = 40 + (hash % 20); // 40-60% lightness
        return `hsla(${h}, ${s}%, ${l}%, ${opacity})`;
    },

    formatDate(epoch) {
        return `Эпоха ${epoch}`;
    }
};