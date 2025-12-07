import { initWorkbench } from './workbench.js';
import { initSimulation, onTabActive } from './simulation.js';
import { initChronicles, loadWorldData } from './chronicles.js';

document.addEventListener('DOMContentLoaded', () => {
    console.log("Initializing Alethea...");

    const state = {
        workbenchInited: false,
        simulationInited: false,
        chroniclesInited: false
    };

    // Helper to run logic based on ID
    const runTabLogic = (targetId) => {
        if (targetId === '#workbench' || targetId === 'workbench') {
            if (!state.workbenchInited) {
                initWorkbench();
                state.workbenchInited = true;
            }
        }

        if (targetId === '#simulation' || targetId === 'simulation') {
            if (!state.simulationInited) {
                initSimulation(); 
                state.simulationInited = true;
            }
            onTabActive();
        }
        
        if (targetId === '#chronicles' || targetId === 'chronicles') {
            if (!state.chroniclesInited) {
                initChronicles();
                state.chroniclesInited = true;
            }
            loadWorldData();
        }
    };

    // 1. Initialize whatever is active by default in HTML
    const activeTab = document.querySelector('.nav-link.active');
    if (activeTab) {
        const target = activeTab.getAttribute('data-bs-target');
        runTabLogic(target);
    }

    // 2. Handle tab switching
    const tabEls = document.querySelectorAll('button[data-bs-toggle="tab"]');
    tabEls.forEach(tabEl => {
        tabEl.addEventListener('shown.bs.tab', event => {
            const targetId = event.target.getAttribute('data-bs-target');
            runTabLogic(targetId);
        });
    });
});