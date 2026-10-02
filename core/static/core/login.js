// ログイン画面の背景演出と BGM ボタン
(() => {
  const bg = document.getElementById('floatBg');
  const counter = document.getElementById('counter');

  if (bg && counter) {
    // 落ち着いた色の泡（CSS変数 --accent に近い寒色系）
    const COLORS = ['#3b5bdb', '#4dabf7', '#748ffc', '#63e6be', '#b197fc'];
    let caught = 0;

    const targetCount = () => Math.min(24, Math.max(10, Math.floor(window.innerWidth / 60)));

    const spawnOne = () => {
      const el = document.createElement('div');
      el.className = 'float-item';

      const size = 18 + Math.random() * 42;              // 18〜60px
      el.style.width = `${size}px`;
      el.style.height = `${size}px`;
      el.style.setProperty('--bubble', COLORS[Math.floor(Math.random() * COLORS.length)]);
      el.style.setProperty('--x', `${Math.random() * 100}vw`);
      el.style.setProperty('--drift', `${Math.random() * 120 - 60}px`);
      el.style.setProperty('--dur', `${14 + Math.random() * 14}s`);
      el.style.animationDelay = `${-Math.random() * 14}s`;

      const pop = () => {
        if (el.classList.contains('pop')) return;
        el.classList.add('pop');
        caught += 1;
        counter.textContent = `消した数：${caught}`;
        setTimeout(() => { el.remove(); spawnOne(); }, 250);
      };
      el.addEventListener('mouseenter', pop);
      el.addEventListener('touchstart', pop, { passive: true });

      bg.appendChild(el);
    };

    for (let i = 0; i < targetCount(); i += 1) spawnOne();

    let resizeTimer = null;
    window.addEventListener('resize', () => {
      clearTimeout(resizeTimer);
      resizeTimer = setTimeout(() => {
        const missing = targetCount() - bg.querySelectorAll('.float-item').length;
        for (let i = 0; i < missing; i += 1) spawnOne();
      }, 200);
    });
  }

  // BGM（音源ファイルがあるときだけボタンが表示される）
  const bgm = document.getElementById('bgm');
  const toggle = document.getElementById('bgm-toggle');
  if (bgm && toggle) {
    toggle.addEventListener('click', async () => {
      try {
        if (bgm.paused) {
          await bgm.play();
          toggle.textContent = '♪ BGM 停止';
          toggle.setAttribute('aria-pressed', 'true');
        } else {
          bgm.pause();
          toggle.textContent = '♪ BGM 再生';
          toggle.setAttribute('aria-pressed', 'false');
        }
      } catch (e) {
        console.log('BGM 再生エラー:', e);
      }
    });
  }
})();
