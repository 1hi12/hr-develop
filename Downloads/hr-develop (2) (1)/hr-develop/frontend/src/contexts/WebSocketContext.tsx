import { createContext, useContext, useEffect, useRef, ReactNode } from 'react';
import { useQueryClient } from '@tanstack/react-query';
import { queryKeys } from '@/lib/query/queryKeys';
import { toast } from 'sonner';

interface WebSocketContextValue {
  ws: WebSocket | null;
  processingCVs: Set<string>;
  addProcessingCV: (filename: string) => void;
  removeProcessingCV: (filename: string) => void;
}

const WebSocketContext = createContext<WebSocketContextValue | null>(null);

export function WebSocketProvider({ children }: { children: ReactNode }) {
  const wsRef = useRef<WebSocket | null>(null);
  const processingCVsRef = useRef<Set<string>>(new Set());
  const queryClient = useQueryClient();
  const reconnectTimeoutRef = useRef<number | null>(null);
  const reconnectAttemptsRef = useRef(0);
  const maxReconnectAttempts = 5;
  const reconnectDelay = 3000; // 3 seconds

  useEffect(() => {
    // Don't create WebSocket in test/SSR environments
    if (typeof window === 'undefined') return;

    const wsProtocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const wsUrl = `${wsProtocol}//${window.location.host}/ws/candidates`;
    
    const connect = () => {
      // Clear any existing reconnection timeout
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }

      console.log('[WS] Connecting to candidates channel...');
      const ws = new WebSocket(wsUrl);
      wsRef.current = ws;

      ws.onopen = () => {
        console.log('[WS] ✅ Connected successfully');
        reconnectAttemptsRef.current = 0; // Reset reconnection counter on success
      };

      ws.onmessage = (event) => {
        try {
          const msg = JSON.parse(event.data);
          
          // NOTE: WebSocket events disabled for synchronous uploads
          // HTTP response handles notifications to avoid duplicates
          if (msg.event === 'cv_processed' || msg.event === 'candidate_added') {
            console.log('[WS] Ignoring cv_processed/candidate_added (handled by HTTP)');
            // HTTP response already showed notification and refreshed cache
          } else if (msg.event === 'cv_processing') {
            console.log('[WS] Ignoring cv_processing (handled by HTTP flow)');
            // HTTP request is synchronous, no need for processing notification
          } else if (msg.event === 'cv_processing_failed') {
            const filename = msg.data?.filename || 'CV';
            processingCVsRef.current.delete(filename);
            
            toast.error(`❌ Échec du traitement de ${filename}`, {
              duration: 4000,
            });
            // Force refresh recent activity specifically
            queryClient.invalidateQueries({ 
              queryKey: ['dashboard', 'recent-activity'],
              refetchType: 'active'
            });
          }
        } catch (err) {
          console.error('[WS] Failed to parse message:', err);
        }
      };

      ws.onerror = (error) => {
        console.warn('[WS] Connection error (will retry if not connected)');
      };

      ws.onclose = (event) => {
        console.log('[WS] Connection closed');
        wsRef.current = null;

        // Only attempt to reconnect if we haven't exceeded max attempts
        if (reconnectAttemptsRef.current < maxReconnectAttempts) {
          reconnectAttemptsRef.current++;
          console.log(`[WS] Reconnecting in ${reconnectDelay / 1000}s (attempt ${reconnectAttemptsRef.current}/${maxReconnectAttempts})...`);
          
          reconnectTimeoutRef.current = window.setTimeout(() => {
            connect();
          }, reconnectDelay);
        } else {
          console.warn('[WS] Max reconnection attempts reached. WebSocket will not reconnect automatically.');
        }
      };
    };

    // Initial connection
    connect();

    // Cleanup on unmount
    return () => {
      console.log('[WS] Cleaning up WebSocket connection...');
      
      // Clear reconnection timeout
      if (reconnectTimeoutRef.current) {
        clearTimeout(reconnectTimeoutRef.current);
        reconnectTimeoutRef.current = null;
      }
      
      // Close WebSocket
      if (wsRef.current) {
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [queryClient]);

  const value: WebSocketContextValue = {
    ws: wsRef.current,
    processingCVs: processingCVsRef.current,
    addProcessingCV: (filename: string) => {
      processingCVsRef.current.add(filename);
    },
    removeProcessingCV: (filename: string) => {
      processingCVsRef.current.delete(filename);
    },
  };

  return (
    <WebSocketContext.Provider value={value}>
      {children}
    </WebSocketContext.Provider>
  );
}

export function useWebSocket() {
  const context = useContext(WebSocketContext);
  if (!context) {
    throw new Error('useWebSocket must be used within WebSocketProvider');
  }
  return context;
}
