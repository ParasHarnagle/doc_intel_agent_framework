/**
 * React Component for Document Intelligence Workflow with Real-time Events
 * 
 * This component demonstrates how to:
 * 1. Start a workflow session
 * 2. Connect to SSE endpoint for real-time updates
 * 3. Display progress events
 * 4. Handle human-in-the-loop approval requests
 */

import React, { useState, useEffect, useRef } from 'react';

interface ProgressEvent {
  phase: string;
  status: 'running' | 'completed';
  timestamp: string;
}

interface ApprovalRequest {
  request_id: string;
  approval_id: string;
  title: string;
  message: string;
  source_uri: string;
  preview: string;
  timestamp: string;
}

interface WorkflowResult {
  result: string;
  timestamp: string;
}

export function WorkflowMonitor() {
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [isConnected, setIsConnected] = useState(false);
  const [progress, setProgress] = useState<ProgressEvent[]>([]);
  const [pendingApproval, setPendingApproval] = useState<ApprovalRequest | null>(null);
  const [result, setResult] = useState<WorkflowResult | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [comment, setComment] = useState('');
  
  const eventSourceRef = useRef<EventSource | null>(null);

  // Start workflow
  const startWorkflow = async (documentUri: string) => {
    try {
      const response = await fetch('/api/workflow/start', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          document_uri: documentUri,
          document_title: 'Tax Return Example',
          page_count: 20
        })
      });
      
      const data = await response.json();
      setSessionId(data.session_id);
      connectToEventStream(data.session_id);
    } catch (err) {
      setError(`Failed to start workflow: ${err}`);
    }
  };

  // Connect to SSE endpoint
  const connectToEventStream = (sessionId: string) => {
    const eventSource = new EventSource(`/api/workflow/${sessionId}/events`);
    eventSourceRef.current = eventSource;

    eventSource.addEventListener('connected', (e) => {
      console.log('Connected to workflow stream:', e.data);
      setIsConnected(true);
    });

    eventSource.addEventListener('workflow_started', (e) => {
      const data = JSON.parse(e.data);
      console.log('Workflow started:', data);
    });

    eventSource.addEventListener('progress', (e) => {
      const data: ProgressEvent = JSON.parse(e.data);
      setProgress(prev => [...prev, data]);
      console.log(`Progress: ${data.phase} - ${data.status}`);
    });

    eventSource.addEventListener('executor_completed', (e) => {
      const data = JSON.parse(e.data);
      console.log(`Executor completed: ${data.executor_id}`);
    });

    eventSource.addEventListener('approval_required', (e) => {
      const data: ApprovalRequest = JSON.parse(e.data);
      setPendingApproval(data);
      console.log('Approval required:', data);
    });

    eventSource.addEventListener('hitl_status', (e) => {
      const data = JSON.parse(e.data);
      console.log(`HITL Status: ${data.status}`);
    });

    eventSource.addEventListener('workflow_completed', (e) => {
      const data: WorkflowResult = JSON.parse(e.data);
      setResult(data);
      console.log('Workflow completed:', data);
      eventSource.close();
      setIsConnected(false);
    });

    eventSource.addEventListener('error', (e: any) => {
      const data = e.data ? JSON.parse(e.data) : { message: 'Connection error' };
      setError(data.message);
      eventSource.close();
      setIsConnected(false);
    });

    eventSource.onerror = () => {
      console.error('EventSource error');
      setIsConnected(false);
    };
  };

  // Submit approval decision
  const submitApproval = async (approved: boolean) => {
    if (!pendingApproval) return;

    try {
      await fetch('/api/workflow/approval', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          request_id: pendingApproval.request_id,
          approval_id: pendingApproval.approval_id,
          approved: approved,
          comment: comment || undefined
        })
      });

      setPendingApproval(null);
      setComment('');
    } catch (err) {
      setError(`Failed to submit approval: ${err}`);
    }
  };

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (eventSourceRef.current) {
        eventSourceRef.current.close();
      }
    };
  }, []);

  return (
    <div className="workflow-monitor">
      <h1>Document Intelligence Workflow</h1>

      {/* Start Workflow Button */}
      {!sessionId && (
        <button onClick={() => startWorkflow('/path/to/document.pdf')}>
          Start Workflow
        </button>
      )}

      {/* Connection Status */}
      {sessionId && (
        <div className="status">
          <span className={isConnected ? 'connected' : 'disconnected'}>
            {isConnected ? '🟢 Connected' : '🔴 Disconnected'}
          </span>
          <span>Session: {sessionId.substring(0, 8)}...</span>
        </div>
      )}

      {/* Progress Timeline */}
      {progress.length > 0 && (
        <div className="progress-timeline">
          <h2>Progress</h2>
          {progress.map((p, idx) => (
            <div key={idx} className={`progress-item ${p.status}`}>
              <span className="icon">
                {p.status === 'running' ? '🔄' : '✅'}
              </span>
              <span className="phase">{p.phase.toUpperCase()}</span>
              <span className="status">{p.status}</span>
              <span className="time">{new Date(p.timestamp).toLocaleTimeString()}</span>
            </div>
          ))}
        </div>
      )}

      {/* Approval Request UI */}
      {pendingApproval && (
        <div className="approval-modal">
          <h2>⏸️ Human Review Required</h2>
          <div className="approval-details">
            <p><strong>Title:</strong> {pendingApproval.title}</p>
            <p><strong>Message:</strong> {pendingApproval.message}</p>
            <p><strong>Source:</strong> {pendingApproval.source_uri}</p>
            <div className="preview">
              <strong>Preview:</strong>
              <pre>{pendingApproval.preview}</pre>
            </div>
          </div>
          
          <div className="approval-actions">
            <textarea
              placeholder="Add comment (optional)"
              value={comment}
              onChange={(e) => setComment(e.target.value)}
              rows={3}
            />
            <div className="buttons">
              <button 
                className="approve" 
                onClick={() => submitApproval(true)}
              >
                ✅ Approve
              </button>
              <button 
                className="reject" 
                onClick={() => submitApproval(false)}
              >
                ❌ Reject
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Final Result */}
      {result && (
        <div className="result">
          <h2>✅ Workflow Completed</h2>
          <pre>{result.result}</pre>
          <p>Completed at: {new Date(result.timestamp).toLocaleString()}</p>
        </div>
      )}

      {/* Error Display */}
      {error && (
        <div className="error">
          <h3>❌ Error</h3>
          <p>{error}</p>
        </div>
      )}
    </div>
  );
}

// CSS Styles (example)
const styles = `
.workflow-monitor {
  max-width: 1200px;
  margin: 0 auto;
  padding: 20px;
  font-family: system-ui, -apple-system, sans-serif;
}

.status {
  display: flex;
  gap: 20px;
  padding: 10px;
  background: #f5f5f5;
  border-radius: 8px;
  margin: 20px 0;
}

.connected { color: #22c55e; }
.disconnected { color: #ef4444; }

.progress-timeline {
  margin: 20px 0;
}

.progress-item {
  display: flex;
  gap: 12px;
  padding: 12px;
  border-left: 3px solid #3b82f6;
  margin: 8px 0;
  background: #f9fafb;
  border-radius: 4px;
}

.progress-item.completed {
  border-left-color: #22c55e;
}

.approval-modal {
  position: fixed;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  background: white;
  padding: 30px;
  border-radius: 12px;
  box-shadow: 0 20px 60px rgba(0,0,0,0.3);
  max-width: 600px;
  width: 90%;
  z-index: 1000;
}

.approval-details {
  margin: 20px 0;
}

.preview {
  margin-top: 15px;
  padding: 15px;
  background: #f9fafb;
  border-radius: 8px;
}

.preview pre {
  margin: 10px 0 0 0;
  white-space: pre-wrap;
  word-break: break-word;
}

.approval-actions textarea {
  width: 100%;
  padding: 10px;
  border: 1px solid #d1d5db;
  border-radius: 6px;
  font-family: inherit;
  margin-bottom: 15px;
}

.buttons {
  display: flex;
  gap: 12px;
  justify-content: flex-end;
}

.buttons button {
  padding: 10px 24px;
  border: none;
  border-radius: 6px;
  font-size: 16px;
  cursor: pointer;
  transition: all 0.2s;
}

.approve {
  background: #22c55e;
  color: white;
}

.approve:hover {
  background: #16a34a;
}

.reject {
  background: #ef4444;
  color: white;
}

.reject:hover {
  background: #dc2626;
}

.result {
  margin: 20px 0;
  padding: 20px;
  background: #f0fdf4;
  border: 2px solid #22c55e;
  border-radius: 8px;
}

.error {
  margin: 20px 0;
  padding: 20px;
  background: #fef2f2;
  border: 2px solid #ef4444;
  border-radius: 8px;
}
`;

export default WorkflowMonitor;
