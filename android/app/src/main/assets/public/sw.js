const CACHE_NAME = 'levantamento-medidas-cache-v1';
// Lista de arquivos a serem armazenados em cache.
// O Capacitor servirá seu index.html e style.css.
// Certifique-se de incluir todos os seus arquivos estáticos críticos.
const urlsToCache = [
    '/', // Isso é importante para que o app funcione offline
    '/index.html',
    '/style.css',
    // Adicione outros arquivos JS personalizados se tiver, por exemplo:
    // '/js/main.js',
    // '/img/logo.png',
    // Você não deve cachear o backend Flask aqui, apenas o frontend.
];

// Evento 'install': Ocorre quando o Service Worker é instalado pela primeira vez.
// É onde você cacheia os ativos estáticos.
self.addEventListener('install', event => {
    console.log('Service Worker: Instalação iniciada...');
    event.waitUntil(
        caches.open(CACHE_NAME)
            .then(cache => {
                console.log('Service Worker: Cache aberto, adicionando arquivos...');
                return cache.addAll(urlsToCache);
            })
            .then(() => self.skipWaiting()) // Força o novo SW a se ativar imediatamente
            .catch(error => {
                console.error('Service Worker: Falha ao cachear arquivos durante a instalação:', error);
            })
    );
});

// Evento 'activate': Ocorre quando o Service Worker é ativado.
// É onde você limpa caches antigos.
self.addEventListener('activate', event => {
    console.log('Service Worker: Ativação iniciada...');
    event.waitUntil(
        caches.keys().then(cacheNames => {
            return Promise.all(
                cacheNames.map(cacheName => {
                    if (cacheName !== CACHE_NAME) {
                        console.log('Service Worker: Deletando cache antigo:', cacheName);
                        return caches.delete(cacheName);
                    }
                })
            );
        }).then(() => self.clients.claim()) // Permite que o novo SW controle os clientes imediatamente
    );
});

// Evento 'fetch': Intercepta requisições de rede.
// Tenta servir do cache primeiro, depois da rede.
self.addEventListener('fetch', event => {
    // Apenas para requisições GET de assets, não API do backend
    if (event.request.method === 'GET' && !event.request.url.includes('/api/') && !event.request.url.includes('onrender.com')) {
        event.respondWith(
            caches.match(event.request)
                .then(response => {
                    // Cache hit - retornar resposta do cache
                    if (response) {
                        return response;
                    }
                    // Nenhum cache hit, tentar rede
                    return fetch(event.request)
                        .then(networkResponse => {
                            // Se a requisição de rede foi bem-sucedida, cachear e retornar
                            if (networkResponse.ok) {
                                return caches.open(CACHE_NAME).then(cache => {
                                    cache.put(event.request, networkResponse.clone());
                                    return networkResponse;
                                });
                            }
                            return networkResponse; // Retorna resposta da rede (pode ser erro)
                        })
                        .catch(error => {
                            console.error('Service Worker: Falha na busca da rede:', error);
                            // Pode-se retornar uma página offline genérica aqui
                            // return caches.match('/offline.html');
                        });
                })
        );
    }
    // Para requisições de API (POST para /salvar_unidade, etc.), não interceptamos com cache aqui.
    // Elas devem ir direto para a rede.
});

// Evento 'sync': Acionado pelo Background Sync API quando a conectividade é restabelecida.
// Esta é a parte crítica para a sincronização offline-first.
self.addEventListener('sync', event => {
    if (event.tag === 'sync-pending-units') {
        console.log('Service Worker: Background Sync acionado para unidades pendentes!');
        event.waitUntil(
            // Chamamos uma função que deve lidar com a lógica de sincronização.
            // Esta função precisa ser independente do DOM e pode estar dentro do SW ou importada.
            // Por simplicidade, vou esboçá-la aqui.
            syncUnitsFromIndexedDBToBackend()
        );
    }
});

// Helper function to sync data from IndexedDB to the backend
async function syncUnitsFromIndexedDBToBackend() {
    console.log('Service Worker: Executando sincronização de IndexedDB para o backend...');
    try {
        const dbPromise = new Promise((resolve, reject) => {
            const request = indexedDB.open(DB_NAME, DB_VERSION);
            request.onupgradeneeded = event => {
                const db = event.target.result;
                if (!db.objectStoreNames.contains(STORE_NAME)) {
                    const objectStore = db.createObjectStore(STORE_NAME, { keyPath: 'id', autoIncrement: true });
                    objectStore.createIndex('local_unidade_index', ['localidade', 'unidade'], { unique: false });
                    objectStore.createIndex('synced_index', 'synced', { unique: false });
                }
            };
            request.onsuccess = event => resolve(event.target.result);
            request.onerror = event => reject(event.target.error);
        });

        const db = await dbPromise;
        const transaction = db.transaction([STORE_NAME], 'readwrite');
        const store = transaction.objectStore(STORE_NAME);
        const index = store.index('synced_index');
        const unitsToSync = await new Promise((resolve, reject) => {
            const req = index.getAll(IDBKeyRange.only(false)); // Buscar unidades com synced: false
            req.onsuccess = () => resolve(req.result);
            req.onerror = event => reject(event.target.error);
        });

        if (unitsToSync.length === 0) {
            console.log('Service Worker: Nenhuma unidade pendente para sincronizar.');
            return;
        }

        for (const unit of unitsToSync) {
            try {
                const backendData = {
                    localidade: unit.localidade,
                    unidade: unit.unidade,
                    data_medicao: unit.data_medicao,
                    responsavel: unit.responsavel,
                    email_destino: unit.email_destino,
                    medidas: unit.medidas
                };

                // Use a URL COMPLETA do seu backend Render aqui!
                const response = await fetch('https://levantamento-medidas.onrender.com/salvar_unidade', {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify(backendData),
                });

                if (response.ok) {
                    const result = await response.json();
                    if (result.status === 'success' || result.status === 'warning') {
                        // Marca a unidade como sincronizada no IndexedDB
                        unit.synced = true;
                        await store.put(unit);
                        console.log(`Service Worker: Unidade '${unit.localidade} - ${unit.unidade}' sincronizada com sucesso!`);
                    } else {
                        console.error(`Service Worker: Erro do servidor ao sincronizar '${unit.localidade} - ${unit.unidade}':`, result.message);
                        // Não marca como sincronizado para tentar novamente depois
                    }
                } else {
                    console.error(`Service Worker: Falha na rede ao sincronizar '${unit.localidade} - ${unit.unidade}'. Status: ${response.status}`);
                    // Não marca como sincronizado para tentar novamente depois
                }
            } catch (innerError) {
                console.error(`Service Worker: Erro ao processar unidade ${unit.id} para sincronização:`, innerError);
                // Continua para a próxima unidade
            }
        }
        await transaction.commit; // Garante que as mudanças no IndexedDB são salvas
        console.log('Service Worker: Sincronização em segundo plano concluída.');

        // Opcional: Notificar o cliente (main thread) para atualizar a UI
        self.clients.matchAll().then(clients => {
            clients.forEach(client => {
                client.postMessage({ type: 'SYNC_COMPLETE', message: 'Sincronização em segundo plano concluída.' });
            });
        });

    } catch (error) {
        console.error('Service Worker: Erro geral na função de sincronização:', error);
    }
}

// Variáveis IndexedDB (precisam ser redefinidas dentro do SW se não houver um módulo compartilhado)
const DB_NAME = 'levantamentoMedidasDB';
const DB_VERSION = 1;
const STORE_NAME = 'unidades';