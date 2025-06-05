import React, { useState, useEffect } from 'react';
import { initializeApp } from 'firebase/app';
import { getAuth, signInAnonymously, signInWithCustomToken, onAuthStateChanged } from 'firebase/auth';
import { getFirestore, doc, setDoc, getDoc, collection, onSnapshot, deleteDoc } from 'firebase/firestore';

// =========================================================================
// ATENÇÃO: SUBSTITUA ESTE OBJETO COM SUAS PRÓPRIAS CREDENCIAIS DO FIREBASE!
// Você encontra estas informações no console do seu projeto Firebase.
// Vá em "Configurações do Projeto" (ícone de engrenagem) -> "Suas aplicações"
// =========================================================================
const firebaseConfig = {
  apiKey: "SUA_API_KEY_AQUI",
  authDomain: "SEU_AUTH_DOMAIN_AQUI",
  projectId: "SEU_PROJECT_ID_AQUI",
  storageBucket: "SEU_STORAGE_BUCKET_AQUI",
  messagingSenderId: "SEU_MESSAGING_SENDER_ID_AQUI",
  appId: "SEU_APP_ID_AQUI"
};
// =========================================================================
// O `appId` abaixo e `initialAuthToken` são específicos do ambiente Canvas.
// No seu próprio app, você não precisa deles, mas podem ficar como estão.
// =========================================================================
const appId = typeof __app_id !== 'undefined' ? __app_id : 'default-app-id';
const initialAuthToken = typeof __initial_auth_token !== 'undefined' ? __initial_auth_token : null;


// Componente principal do aplicativo
function App() {
  const [db, setDb] = useState(null);
  const [auth, setAuth] = useState(null);
  const [userId, setUserId] = useState(null);
  const [isAuthReady, setIsAuthReady] = useState(false);

  // Estados para os dados da unidade
  const [unitName, setUnitName] = useState('');
  const [responsible, setResponsible] = useState('');
  const [employees, setEmployees] = useState('');
  const [hasLawn, setHasLawn] = useState(false);
  const [hasParking, setHasParking] = useState(false);
  const [hasDressingRoom, setHasDressingRoom] = useState(false);
  const [hasVaccineRoom, setHasVaccineRoom] = useState(false);
  const [hasHighWindows, setHasHighWindows] = useState(false);

  // Estados para as medidas
  const [windows, setWindows] = useState([]);
  const [internalAreas, setInternalAreas] = useState([]);
  const [externalAreas, setExternalAreas] = useState([]);
  const [bathrooms, setBathrooms] = useState([]);

  // Estado para o modo de edição de medida
  const [editingMeasurement, setEditingMeasurement] = useState(null);
  const [measurementType, setMeasurementType] = useState('');

  // Estado para a navegação entre as telas
  const [currentPage, setCurrentPage] = useState('unitDetails'); // 'unitDetails', 'windows', 'internal', 'external', 'bathrooms', 'summary'
  const [message, setMessage] = useState('');

  // Inicialização do Firebase e autenticação
  useEffect(() => {
    try {
      const firebaseApp = initializeApp(firebaseConfig);
      const firestore = getFirestore(firebaseApp);
      const firebaseAuth = getAuth(firebaseApp);

      setDb(firestore);
      setAuth(firebaseAuth);

      const unsubscribe = onAuthStateChanged(firebaseAuth, async (user) => {
        if (user) {
          setUserId(user.uid);
        } else {
          try {
            // Em seu próprio aplicativo, você pode usar signInAnonymously() diretamente,
            // ou implementar outro método de autenticação (e-mail/senha, Google, etc.).
            // initialAuthToken é para o ambiente Canvas.
            if (initialAuthToken) {
              await signInWithCustomToken(firebaseAuth, initialAuthToken);
            } else {
              await signInAnonymously(firebaseAuth);
            }
          } catch (error) {
            console.error('Erro ao autenticar:', error);
            setMessage('Erro ao iniciar sessão: ' + error.message);
          }
        }
        setIsAuthReady(true);
      });

      return () => unsubscribe();
    } catch (error) {
      console.error('Erro na inicialização do Firebase:', error);
      setMessage('Erro na inicialização do aplicativo: ' + error.message);
    }
  }, []);

  // Carregar dados da unidade e medidas do Firestore
  useEffect(() => {
    if (db && userId && isAuthReady) {
      // Caminho para os dados privados da unidade
      const unitDocRef = doc(db, `/artifacts/<span class="math-inline">\{appId\}/users/</span>{userId}/unitData/main`);

      // Listener para os dados da unidade
      const unsubscribeUnit = onSnapshot(unitDocRef, (docSnap) => {
        if (docSnap.exists()) {
          const data = docSnap.data();
          setUnitName(data.unitName || '');
          setResponsible(data.responsible || '');
          setEmployees(data.employees || '');
          setHasLawn(data.hasLawn || false);
          setHasParking(data.hasParking || false);
          setHasDressingRoom(data.hasDressingRoom || false);
          setHasVaccineRoom(data.hasVaccineRoom || false);
          setHasHighWindows(data.hasHighWindows || false);
        } else {
          console.log("Nenhum dado de unidade encontrado.");
        }
      }, (error) => {
        console.error("Erro ao carregar dados da unidade:", error);
        setMessage("Erro ao carregar dados da unidade: " + error.message);
      });

      // Listeners para as coleções de medidas
      const measurementTypes = [
        { type: 'windows', setter: setWindows },
        { type: 'internalAreas', setter: setInternalAreas },
        { type: 'externalAreas', setter: setExternalAreas },
        { type: 'bathrooms', setter: setBathrooms }
      ];

      const unsubscribesMeasurements = measurementTypes.map(({ type, setter }) => {
        // Caminho da coleção para medidas no Firestore: artifacts/{appId}/users/{userId}/measurements_{tipo}
        // Ex: artifacts/seu-app-id/users/seu-user-id/measurements_windows
        const colRef = collection(db, `/artifacts/<span class="math-inline">\{appId\}/users/</span>{userId}/measurements_${type}`);
        return onSnapshot(colRef, (snapshot) => {
          const loadedData = [];
          snapshot.forEach(doc => {
            loadedData.push({ id: doc.id, ...doc.data() });
          });
          setter(loadedData);
        }, (error) => {
          console.error(`Erro ao carregar ${type}:`, error);
          setMessage(`Erro ao carregar ${type}: ` + error.message);
        });
      });

      return () => {
        unsubscribeUnit();
        unsubscribesMeasurements.forEach(unsub => unsub());
      };
    }
  }, [db, userId, isAuthReady]);

  // Função para salvar os dados da unidade
  const saveUnitData = async () => {
    if (!db || !userId) {
      setMessage('Firebase não inicializado ou usuário não autenticado.');
      return;
    }
    try {
      const unitDocRef = doc(db, `/artifacts/<span class="math-inline">\{appId\}/users/</span>{userId}/unitData/main`);
      await setDoc(unitDocRef, {
        unitName,
        responsible,
        employees: Number(employees), // Garantir que employees seja um número
        hasLawn,
        hasParking,
        hasDressingRoom,
        hasVaccineRoom,
        hasHighWindows,
      }, { merge: true });
      setMessage('Dados da unidade salvos com sucesso!');
    } catch (error) {
      console.error('Erro ao salvar dados da unidade:', error);
      setMessage('Erro ao salvar dados da unidade: ' + error.message);
    }
  };

  // Componente para adicionar/editar medidas (Vidros, Ambientes, Banheiros)
  const MeasurementForm = ({ onSubmit, onClose, initialData, type }) => {
    const [length, setLength] = useState(initialData?.length || '');
    const [width, setWidth] = useState(initialData?.width || '');
    const [description, setDescription] = useState(initialData?.description || '');

    const calculateArea = () => {
      const len = parseFloat(length);
      const wid = parseFloat(width);
      return (isNaN(len) || isNaN(wid) || len < 0 || wid < 0) ? 0 : (len * wid).toFixed(2);
    };

    const handleSubmit = () => {
      if (length === '' || width === '' || parseFloat(length) < 0 || parseFloat(width) < 0) {
        setMessage('Por favor, insira valores positivos para comprimento e largura.');
        return;
      }
      onSubmit({
        id: initialData?.id || Date.now().toString(), // Usar ID existente ou gerar um novo
        length: parseFloat(length),
        width: parseFloat(width),
        area: parseFloat(calculateArea()),
        description: description,
        type: type // Adiciona o tipo de medida
      });
      onClose();
    };

    return (
      <div className="fixed inset-0 bg-gray-600 bg-opacity-50 flex justify-center items-center p-4">
        <div className="bg-white p-6 rounded-lg shadow-lg w-full max-w-md">
          <h3 className="text-lg font-bold mb-4 text-gray-800">{initialData ? 'Editar' : 'Adicionar'} Medida de {
            type === 'windows' ? 'Vidro' :
            type === 'internalAreas' ? 'Ambiente Interno' :
            type === 'externalAreas' ? 'Ambiente Externo' :
            'Sanitário-Vestiário'
          }</h3>
          <input
            type="number"
            placeholder="Comprimento (m)"
            value={length}
            onChange={(e) => setLength(e.target.value)}
            className="w-full p-2 mb-3 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <input
            type="number"
            placeholder="Largura (m)"
            value={width}
            onChange={(e) => setWidth(e.target.value)}
            className="w-full p-2 mb-3 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <input
            type="text"
            placeholder="Descrição (ex: Janela da sala)"
            value={description}
            onChange={(e) => setDescription(e.target.value)}
            className="w-full p-2 mb-3 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
          />
          <p className="text-gray-700 mb-4">Área Calculada: {calculateArea()} m²</p>
          <div className="flex justify-end space-x-3">
            <button
              onClick={onClose}
              className="px-4 py-2 bg-gray-300 text-gray-800 rounded-md hover:bg-gray-400 transition-colors"
            >
              Cancelar
            </button>
            <button
              onClick={handleSubmit}
              className="px-4 py-2 bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors"
            >
              {initialData ? 'Salvar' : 'Adicionar'}
            </button>
          </div>
        </div>
      </div>
    );
  };

  // Função para adicionar ou atualizar uma medida no Firestore
  const handleAddOrUpdateMeasurement = async (data, type) => {
    if (!db || !userId) {
      setMessage('Firebase não inicializado ou usuário não autenticado.');
      return;
    }
    try {
      // Caminho da coleção para medidas no Firestore
      const measurementColRef = collection(db, `/artifacts/<span class="math-inline">\{appId\}/users/</span>{userId}/measurements_${type}`);
      const docRef = doc(measurementColRef, data.id); // Cria ou usa um doc ref com ID específico
      await setDoc(docRef, data);
      setMessage(`Medida de ${type} salva com sucesso!`);
      setEditingMeasurement(null);
    } catch (error) {
      console.error(`Erro ao salvar medida de ${type}:`, error);
      setMessage(`Erro ao salvar medida de ${type}: ` + error.message);
    }
  };

  // Função para deletar uma medida do Firestore
  const handleDeleteMeasurement = async (id, type) => {
    if (!db || !userId) {
      setMessage('Firebase não inicializado ou usuário não autenticado.');
      return;
    }
    try {
      // Caminho da coleção para medidas no Firestore
      const measurementDocRef = doc(db, `/artifacts/<span class="math-inline">\{appId\}/users/</span>{userId}/measurements_${type}/${id}`);
      await deleteDoc(measurementDocRef);
      setMessage(`Medida de ${type} deletada com sucesso!`);
    } catch (error) {
      console.error(`Erro ao deletar medida de ${type}:`, error);
      setMessage(`Erro ao deletar medida de ${type}: ` + error.message);
    }
  };

  // Renderiza a lista de medidas para um tipo específico
  const renderMeasurementList = (measurements, type) => (
    <div className="flex flex-col gap-3 p-4">
      {measurements.length === 0 ? (
        <p className="text-center text-gray-500">Nenhuma medida cadastrada.</p>
      ) : (
        measurements.map((m, index) => (
          <div key={m.id || index} className="bg-white p-4 rounded-lg shadow-sm flex items-center justify-between">
            <div>
              <p className="text-gray-900 font-medium">
                {m.description || `Medida ${index + 1}`}: {m.length}m x {m.width}m
              </p>
              <p className="text-gray-600 text-sm">Área: {m.area} m²</p>
            </div>
            <div className="flex space-x-2">
              <button
                onClick={() => {
                  setEditingMeasurement(m);
                  setMeasurementType(type);
                }}
                className="p-2 bg-yellow-500 text-white rounded-md hover:bg-yellow-600 transition-colors"
              >
                <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
                  <path d="M13.586 3.586a2 2 0 112.828 2.828l-.793.793-2.828-2.828.793-.793zm-4.646 2.071L2 14.828V18h3.172l8.257-8.257-3.172-3.172z" />
                </svg>
              </button>
              <button
                onClick={() => handleDeleteMeasurement(m.id, type)}
                className="p-2 bg-red-500 text-white rounded-md hover:bg-red-600 transition-colors"
              >
                <svg xmlns="http://www.w3.org/2000/svg" className="h-5 w-5" viewBox="0 0 20 20" fill="currentColor">
                  <path fillRule="evenodd" d="M9 2a1 1 0 00-.894.553L7.382 4H4a1 1 0 000 2v10a2 2 0 002 2h8a2 2 0 002-2V6a1 1 0 100-2h-3.382l-.724-1.447A1 1 0 0011 2H9zM7 8a1 1 0 012 0v6a1 1 0 11-2 0V8zm5-1a1 1 0 00-1 1v6a1 1 0 102 0V8a1 1 0 00-1-1z" clipRule="evenodd" />
                </svg>
              </button>
            </div>
          </div>
        ))
      )}
      <button
        onClick={() => {
          setEditingMeasurement(null);
          setMeasurementType(type);
        }}
        className="mt-4 px-4 py-2 bg-green-600 text-white rounded-md hover:bg-green-700 transition-colors"
      >
        Adicionar Nova Medida
      </button>
    </div>
  );

  // Renderização das telas
  const renderPage = () => {
    switch (currentPage) {
      case 'unitDetails':
        return (
          <div className="p-4 space-y-4">
            <h2 className="text-xl font-bold text-gray-800">Dados Básicos da Unidade</h2>
            <input
              type="text"
              placeholder="Nome da Unidade"
              value={unitName}
              onChange={(e) => setUnitName(e.target.value)}
              className="w-full p-3 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            <input
              type="text"
              placeholder="Responsável"
              value={responsible}
              onChange={(e) => setResponsible(e.target.value)}
              className="w-full p-3 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
            />
            <input
              type="number"
              placeholder="Quantidade de Funcionários"
              value={employees}
              onChange={(e) => setEmployees(e.target.value)}
              className="w-full p-3 border border-gray-300 rounded-md focus:outline-none focus:ring-2 focus:ring-blue-500"
            />

            <div className="grid grid-cols-2 gap-3 text-gray-800">
              <label className="flex items-center space-x-2">
                <input
                  type="checkbox"
                  checked={hasLawn}
                  onChange={(e) => setHasLawn(e.target.checked)}
                  className="form-checkbox h-5 w-5 text-blue-600 rounded"
                />
                <span>Gramado</span>
              </label>
              <label className="flex items-center space-x-2">
                <input
                  type="checkbox"
                  checked={hasParking}
                  onChange={(e) => setHasParking(e.target.checked)}
                  className="form-checkbox h-5 w-5 text-blue-600 rounded"
                />
                <span>Estacionamento</span>
              </label>
              <label className="flex items-center space-x-2">
                <input
                  type="checkbox"
                  checked={hasDressingRoom}
                  onChange={(e) => setHasDressingRoom(e.target.checked)}
                  className="form-checkbox h-5 w-5 text-blue-600 rounded"
                />
                <span>Sala de Curativo</span>
              </label>
              <label className="flex items-center space-x-2">
                <input
                  type="checkbox"
                  checked={hasVaccineRoom}
                  onChange={(e) => setHasVaccineRoom(e.target.checked)}
                  className="form-checkbox h-5 w-5 text-blue-600 rounded"
                />
                <span>Sala de Vacina</span>
              </label>
              <label className="flex items-center space-x-2">
                <input
                  type="checkbox"
                  checked={hasHighWindows}
                  onChange={(e) => setHasHighWindows(e.target.checked)}
                  className="form-checkbox h-5 w-5 text-blue-600 rounded"
                />
                <span>Vidros Altos</span>
              </label>
            </div>
            <button
              onClick={saveUnitData}
              className="w-full py-3 bg-blue-600 text-white rounded-md hover:bg-blue-700 transition-colors"
            >
              Salvar Dados da Unidade
            </button>
          </div>
        );
      case 'windows':
        return (
          <div className="p-4">
            <h2 className="text-xl font-bold text-gray-800 mb-4">Medidas dos Vidros</h2>
            {renderMeasurementList(windows, 'windows')}
          </div>
        );
      case 'internal':
        return (
          <div className="p-4">
            <h2 className="text-xl font-bold text-gray-800 mb-4">Medidas dos Ambientes Internos</h2>
            {renderMeasurementList(internalAreas, 'internalAreas')}
          </div>
        );
      case 'external':
        return (
          <div className="p-4">
            <h2 className="text-xl font-bold text-gray-800 mb-4">Medidas dos Ambientes Externos</h2>
            {renderMeasurementList(externalAreas, 'externalAreas')}
          </div>
        );
      case 'bathrooms':
        return (
          <div className="p-4">
            <h2 className="text-xl font-bold text-gray-800 mb-4">Medidas dos Sanitários-Vestiários</h2>
            {renderMeasurementList(bathrooms, 'bathrooms')}
          </div>
        );
      case 'summary':
        return (
          <div className="p-4">
            <h2 className="text-xl font-bold text-gray-800 mb-4">Resumo dos Dados da Unidade</h2>
            <div className="bg-white p-6 rounded-lg shadow-md mb-6">
              <h3 className="text-lg font-semibold text-gray-800 mb-3">Dados Básicos:</h3>
              <p className="text-gray-700"><strong>Unidade:</strong> {unitName || 'Não informado'}</p>
              <p className="text-gray-700"><strong>Responsável:</strong> {responsible || 'Não informado'}</p>
              <p className="text-gray-700"><strong>Funcionários:</strong> {employees || 'Não informado'}</p>
              <p className="text-gray-700">
                <strong>Características:</strong>{' '}
                {[
                  hasLawn && 'Gramado',
                  hasParking && 'Estacionamento',
                  hasDressingRoom && 'Sala de Curativo',
                  hasVaccineRoom && 'Sala de Vacina',
                  hasHighWindows && 'Vidros Altos',
                ].filter(Boolean).join(', ') || 'Nenhuma selecionada'}
              </p>
            </div>

            {/* Simulação de exportação de dados para visualização */}
            <div className="bg-white p-6 rounded-lg shadow-md mb-6">
              <h3 className="text-lg font-semibold text-gray-800 mb-3">Dados Detalhados (Simulação de Planilha):</h3>
              <p className="text-gray-600 text-sm mb-4">
                Este formato representa os dados que seriam exportados para uma planilha Excel. Você pode copiar este texto ou, em um aplicativo real, um serviço de backend seria usado para gerar e enviar o arquivo Excel.
              </p>
              <pre className="bg-gray-100 p-4 rounded-md text-sm whitespace-pre-wrap break-all max-h-96 overflow-auto">
                {JSON.stringify({
                  dadosBasicos: {
                    unitName,
                    responsible,
                    employees,
                    hasLawn,
                    hasParking,
                    hasDressingRoom,
                    hasVaccineRoom,
                    hasHighWindows,
                  },
                  medidasVidros: windows,
                  medidasAmbientesInternos: internalAreas,
                  medidasAmbientesExternos: externalAreas,
                  medidasSanitariosVestiarios: bathrooms,
                }, null, 2)}
              </pre>
            </div>

            <p className="text-center text-gray-600 mt-4">
              ID do Usuário: {userId || 'Autenticando...'}
            </p>
          </div>
        );
      default:
        return null;
    }
  };

  return (
    <div className="min-h-screen bg-gray-100 font-sans text-gray-900 flex flex-col">
      <style>
        {`
          @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');
          body {
            font-family: 'Inter', sans-serif;
          }
          /* Custom checkbox styles for better appearance */
          input[type="checkbox"].form-checkbox {
            appearance: none;
            -webkit-appearance: none;
            -moz-appearance: none;
            height: 1.25rem; /* h-5 */
            width: 1.25rem;  /* w-5 */
            border: 2px solid #D1D5DB; /* gray-300 */
            border-radius: 0.25rem; /* rounded */
            cursor: pointer;
            display: inline-block;
            vertical-align: middle;
            position: relative;
            outline: none;
          }
          input[type="checkbox"].form-checkbox:checked {
            background-color: #3B82F6; /* blue-600 */
            border-color: #3B82F6; /* blue-600 */
          }
          input[type="checkbox"].form-checkbox:checked::after {
            content: '';
            display: block;
            width: 0.5rem; /* approx */
            height: 0.75rem; /* approx */
            border: solid white;
            border-width: 0 2px 2px 0;
            transform: rotate(45deg);
            position: absolute;
            left: 0.35rem; /* fine tune position */
            top: 0.1rem; /* fine tune position */
          }
        `}
      </style>

      {/* Cabeçalho fixo com o nome do aplicativo e mensagem */}
      <header className="bg-gradient-to-r from-blue-600 to-blue-800 text-white p-4 shadow-lg sticky top-0 z-10 flex flex-col items-center justify-center rounded-b-lg">
        <h1 className="text-2xl font-bold mb-1">Gerenciador de Unidades</h1>
        {message && (
          <div className="bg-white text-blue-800 text-sm py-1 px-3 rounded-full mt-2 shadow-inner">
            {message}
          </div>
        )}
      </header>

      {/* Navegação por abas */}
      <nav className="bg-white shadow-md p-2 flex justify-center flex-wrap gap-2 sticky top-16 z-10 border-b border-gray-200">
        <button
          onClick={() => setCurrentPage('unitDetails')}
          className={`px-4 py-2 rounded-md transition-colors text-sm font-medium ${
            currentPage === 'unitDetails' ? 'bg-blue-500 text-white shadow' : 'bg-gray-200 text-gray-700 hover:bg-blue-100'
          }`}
        >
          Dados da Unidade
        </button>
        <button
          onClick={() => setCurrentPage('windows')}
          className={`px-4 py-2 rounded-md transition-colors text-sm font-medium ${
            currentPage === 'windows' ? 'bg-blue-500 text-white shadow' : 'bg-gray-200 text-gray-700 hover:bg-blue-100'
          }`}
        >
          Vidros
        </button>
        <button
          onClick={() => setCurrentPage('internal')}
          className={`px-4 py-2 rounded-md transition-colors text-sm font-medium ${
            currentPage === 'internal' ? 'bg-blue-500 text-white shadow' : 'bg-gray-200 text-gray-700 hover:bg-blue-100'
          }`}
        >
          Áreas Internas
        </button>
        <button
          onClick={() => setCurrentPage('external')}
          className={`px-4 py-2 rounded-md transition-colors text-sm font-medium ${
            currentPage === 'external' ? 'bg-blue-500 text-white shadow' : 'bg-gray-200 text-gray-700 hover:bg-blue-100'
          }`}
        >
          Áreas Externas
        </button>
        <button
          onClick={() => setCurrentPage('bathrooms')}
          className={`px-4 py-2 rounded-md transition-colors text-sm font-medium ${
            currentPage === 'bathrooms' ? 'bg-blue-500 text-white shadow' : 'bg-gray-200 text-gray-700 hover:bg-blue-100'
          }`}
        >
          Sanitários
        </button>
        <button
          onClick={() => setCurrentPage('summary')}
