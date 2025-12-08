// js/api.js

const IS_GH_PAGES = window.location.hostname.includes('github.io') || window.location.hostname.includes('localhost'); 
const STATIC_BASE = 'world_output';

export const api = {
    // Экспортируем флаг, чтобы simulation.js мог его проверить
    isStatic: IS_GH_PAGES,

    get: async (endpoint) => {
        try {
            if (IS_GH_PAGES) return await mockGet(endpoint);
            
            const res = await fetch(endpoint);
            if (!res.ok) throw new Error("API unavailable");
            return await res.json();
        } catch (e) {
            console.warn(`[API] Switch to static: ${e.message}`);
            // Если API упал, переключаемся в статику на лету
            api.isStatic = true; 
            return await mockGet(endpoint);
        }
    },

    post: async (endpoint, body) => {
        if (IS_GH_PAGES || api.isStatic) {
            console.log(`[Mock POST] ${endpoint}`, body);
            return { success: true, message: "Static mode: action simulated" };
        }
        
        const res = await fetch(endpoint, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(body)
        });
        return await res.json();
    }
};

async function mockGet(endpoint) {
    console.log(`[Mock GET] ${endpoint}`);

    // 1. Граф и сущности
    if (endpoint.includes('/world/graph') || endpoint.includes('latest_graph') || endpoint.includes('latest_entities')) {
        const data = await fetchJson(`${STATIC_BASE}/world_final.json`);
        // Для latest_entities возвращаем массив, для графа - как есть
        if (endpoint.includes('latest_entities')) {
             return { entities: data.entities ? Object.values(data.entities) : [] };
        }
        return data;
    }

    // 2. Карта (Layout)
    if (endpoint.includes('latest_layout')) {
        const data = await fetchJson(`${STATIC_BASE}/world_final.json`);
        // Если в JSON нет layout (старая версия), возвращаем заглушку
        return data.layout || { width: 10, height: 10, cells: {} };
    }

    // 3. Логи истории
    if (endpoint.includes('history_logs')) {
        try {
            const text = await fetchText(`${STATIC_BASE}/history.jsonl`);
            // Разбиваем JSONL
            const logs = text.trim().split('\n')
                .map(line => { try { return JSON.parse(line); } catch(e){ return null; }})
                .filter(Boolean);
            return { logs: logs };
        } catch (e) {
            console.warn("History logs not found or empty");
            return { logs: [] };
        }
    }

    if (endpoint.includes('/configs')) return [];
    return {};
}

async function fetchJson(path) {
    const res = await fetch(path);
    if (!res.ok) throw new Error(`404: ${path}`);
    return await res.json();
}

async function fetchText(path) {
    const res = await fetch(path);
    if (!res.ok) throw new Error(`404: ${path}`);
    return await res.text();
}