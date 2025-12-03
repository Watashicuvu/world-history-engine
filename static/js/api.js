// static/js/api.js

export const api = {
    async get(url) {
        const res = await fetch(url);
        if (!res.ok) throw new Error(`API Error: ${res.statusText}`);
        return res.json();
    },

    async post(url, data) {
        const res = await fetch(url, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(data)
        });
        if (!res.ok) {
            const err = await res.json();
            throw new Error(err.detail || `API Error: ${res.statusText}`);
        }
        return res.json();
    }
};