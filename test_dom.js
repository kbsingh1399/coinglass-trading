const getTxt = (el) => el.innerText || '';

// Mock elements based on DOM_Analysis.md
const mockLeafValEls = [
    { className: 'valueTitle-l31H9iuA', innerText: 'Long' },
    { className: 'valueTitle-l31H9iuA', innerText: 'No Filter' },
    { className: 'valueValue-l31H9iuA', innerText: '24.981K' },
    { className: 'valueValue-l31H9iuA', innerText: '-950.61' } // using unicode minus \u2212
];

let valStrs = mockLeafValEls
    .filter(v => {
        let cls = (v.className || '').toString().toLowerCase();
        return !cls.includes('title') && !cls.includes('name') && !cls.includes('source') && !cls.includes('alias');
    })
    .map(v => getTxt(v))
    .filter(v => v && v !== 'N/A' && !v.includes('\n'));

console.log('valStrs:', valStrs);

let numStrs = valStrs.map(s => {
    if (s.includes('\u2205') || s.includes('Ø') || s.includes('ø') || s.trim() === '') {
        return '0';
    }
    let normalized = s.replace(/[\u2212-]/g, '-');
    let m = normalized.match(/[-+]?\d*\.?\d+[KkMmBb]?/);
    return m ? m[0] : '0';
});

console.log('numStrs:', numStrs);
let targets = numStrs.slice(-2);
console.log('targets:', targets);
