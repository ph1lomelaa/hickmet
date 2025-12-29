# 📝 ОБНОВЛЕНИЕ config.js НА GITHUB PAGES

## ✅ ЧТО СДЕЛАНО В БОТЕ

Бот теперь передает `api_url` параметр при открытии WebApp:
- ✅ В `.env.local` установлен `API_BASE_URL=http://localhost:8000`
- ✅ Бот передает этот URL в WebApp через параметр `api_url`

---

## 📋 ЧТО НУЖНО ИЗМЕНИТЬ НА GITHUB PAGES

Зайди в свой репозиторий **ph1lomelaa.github.io** (или как называется) и измени файл **config.js**:

### Старый код (сейчас):

```javascript
(function() {
  const defaultApiUrl = 'https://marxist-noell-uslima2005-12a246c3.koyeb.app';
  if (!window.BULL_API_URL) {
    window.BULL_API_URL = defaultApiUrl;
  }
})();
```

### Новый код (замени на это):

```javascript
(function() {
  // Проверяем есть ли api_url в параметрах URL
  const urlParams = new URLSearchParams(window.location.search);
  const apiUrlParam = urlParams.get('api_url');

  // Если есть параметр api_url - используем его (для локального тестирования)
  // Иначе используем production URL
  const defaultApiUrl = apiUrlParam || 'https://marxist-noell-uslima2005-12a246c3.koyeb.app';

  if (!window.BULL_API_URL) {
    window.BULL_API_URL = defaultApiUrl;
  }

  // Для отладки
  console.log('🌐 BULL_API_URL:', window.BULL_API_URL);
})();
```

---

## 🎯 КАК ЭТО РАБОТАЕТ

### Для локального тестирования:
1. Запускаешь локальный API: `./run_api_test.sh`
2. Запускаешь бота: `./run_test.sh`
3. Бот открывает WebApp с URL:
   ```
   https://ph1lomelaa.github.io/book/index.html?api_url=http://localhost:8000&pilgrims=...
   ```
4. config.js читает `api_url` из URL и устанавливает `window.BULL_API_URL = http://localhost:8000`
5. ✅ **Все запросы идут на локальный API с TEST таблицей!**

### Для production:
1. Бот открывает WebApp БЕЗ параметра `api_url` (потому что `API_BASE_URL` пустой в production)
2. config.js использует дефолтный Koyeb URL
3. ✅ **Все запросы идут на Koyeb с production таблицами**

---

## 📝 COMMIT НА GITHUB

После изменения config.js:

```bash
git add config.js
git commit -m "Support api_url parameter for local testing"
git push origin main
```

Подожди 1-2 минуты пока GitHub Pages обновится.

---

## 🧪 ПРОВЕРКА

После обновления config.js:

1. Запусти локальный API: `./run_api_test.sh`
2. Запусти бота: `./run_test.sh`
3. Открой бота в Telegram
4. Начни создавать бронь
5. Когда откроется WebApp - открой Developer Console (F12)
6. Должен увидеть: `🌐 BULL_API_URL: http://localhost:8000`

✅ **Если видишь localhost:8000 - всё работает!**

---

## ⚠️ ВАЖНО

После изменения config.js на GitHub:
- ✅ Production будет работать как обычно (Koyeb)
- ✅ Локальное тестирование будет использовать localhost API
- ✅ Автоматическое переключение по параметру `api_url`

**Это безопасно и не сломает production!** 🚀
