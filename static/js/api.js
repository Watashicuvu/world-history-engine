// js/api.js

// Определяем, запущены ли мы на GitHub Pages или локально без сервера
const IS_GH_PAGES = window.location.hostname.includes('github.io');
const STATIC_BASE = 'world_output'; // Путь к папке с JSON

export const api = {
    // Основной метод GET
    get: async (endpoint) => {
        console.log(`[API] GET ${endpoint}`);
        
        try {
            // Если мы на GitHub Pages, СРАЗУ идем в статический режим
            if (IS_GH_PAGES) {
                return await mockGet(endpoint);
            }
            
            // Иначе пробуем реальный API
            const res = await fetch(endpoint);
            if (!res.ok) throw new Error("API unavailable");
            return await res.json();
            
        } catch (e) {
            console.warn(`[API] Switch to static mode due to: ${e.message}`);
            return await mockGet(endpoint);
        }
    },

    // Метод POST (в статике просто имитируем успех)
    post: async (endpoint, body) => {
        console.log(`[API] POST ${endpoint}`, body);
        if (IS_GH_PAGES) {
            alert("В демо-режиме (Static) нельзя создавать новые миры, только просматривать готовые.");
            return { success: true };
        }
        
        const res = await fetch(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });
        return await res.json();
    }
};

// --- ФУНКЦИИ-ЗАГЛУШКИ (MOCKS) ---

async function mockGet(endpoint) {
    // 1. Запрос графа (Chronicles)
    if (endpoint.includes('/world/graph') || endpoint.includes('latest_graph')) {
        return await fetchJson(`${STATIC_BASE}/world_final.json`);
    }

    // 2. Запрос сущностей для карты (Simulation)
    if (endpoint.includes('latest_entities')) {
        const data = await fetchJson(`${STATIC_BASE}/world_final.json`);
        // Если в JSON'е entities лежат объектом, превращаем в массив для симуляции
        const entities = data.entities ? Object.values(data.entities) : [];
        return { entities: entities };
    }

    // 3. Запрос ландшафта/карты (Simulation Layout)
    if (endpoint.includes('latest_layout')) {
        const data = await fetchJson(`${STATIC_BASE}/world_final.json`);
        // Проверяем, есть ли layout внутри world_final.json (зависит от версии вашего генератора)
        // Если нет — возвращаем пустую заглушку, чтобы код не падал
        return data.layout || { width: 10, height: 10, cells: {} };
    }

    // 4. Логи истории (Simulation Logs)
    if (endpoint.includes('history_logs')) {
        const text = await fetchText(`${STATIC_BASE}/history.jsonl`);
        // Разбиваем JSONL на массив объектов
        const logs = text.trim().split('\n').map(line => {
            try { return JSON.parse(line); } catch (e) { return null; }
        }).filter(Boolean);
        return { logs: logs };
    }

    // 5. Конфиги (Workbench) — возвращаем пустые списки
    if (endpoint.includes('/configs')) {
        return [];
    }

    return {};
}

// Хелперы для загрузки файлов
async function fetchJson(path) {
    const res = await fetch(path);
    if (!res.ok) throw new Error(`File not found: ${path}`);
    return await res.json();
}

async function fetchText(path) {
    const res = await fetch(path);
    if (!res.ok) throw new Error(`File not found: ${path}`);
    return await res.text();
}