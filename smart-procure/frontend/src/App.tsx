import Layout from './components/Layout';
import ChatPanel from './components/ChatPanel';
import UniverSheet from './components/UniverSheet';
import { useProcureState } from './hooks/useProcureState';

function App() {
  const { sheetData, chatHistory, isThinking, handleSendMessage, handleFileUpload, handleSheetDataChange, clearChatHistory } = useProcureState();

  return (
    <Layout
      left={
        <ChatPanel 
          history={chatHistory} 
          onSend={handleSendMessage}
          onFileUpload={handleFileUpload}
          isThinking={isThinking}
          onClear={clearChatHistory}
        />
      }
      right={
        <UniverSheet data={sheetData} onDataChange={handleSheetDataChange} />
      }
    />
  );
}

export default App;
