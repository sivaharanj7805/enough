'use client';

import { useState, useCallback, useRef, useEffect } from 'react';
import { Sparkles, Send, ArrowLeft } from 'lucide-react';
import Link from 'next/link';
import { useSite } from '@/lib/hooks/useSite';
import { useAuth } from '@/lib/hooks/useAuth';
import { apiUrl } from '@/lib/api';

interface ChatMessage {
  id: string;
  role: 'user' | 'oracle';
  content: string;
  timestamp: number;
}

const SUGGESTIONS = [
  "What's my best performing cluster?",
  "Which posts should I update first?",
  "Why is my health score low?",
  "What's cannibalizing my top post?",
];

/** Turn markdown-ish references into clickable links */
function renderMessageContent(content: string) {
  // Detect patterns like [Post: title](/posts/id) or /clusters/id or URLs
  const parts = content.split(/(\[.*?\]\(.*?\)|https?:\/\/\S+|\/(?:posts|clusters)\/[a-zA-Z0-9-]+)/g);

  return parts.map((part, i) => {
    // Markdown link: [text](url)
    const mdMatch = part.match(/^\[(.*?)\]\((.*?)\)$/);
    if (mdMatch) {
      return (
        <Link key={i} href={mdMatch[2]} className="underline text-[#3B82F6] hover:text-[#60A5FA]">
          {mdMatch[1]}
        </Link>
      );
    }
    // Internal path: /posts/... or /clusters/...
    if (/^\/(?:posts|clusters)\/[a-zA-Z0-9-]+$/.test(part)) {
      return (
        <Link key={i} href={part} className="underline text-[#3B82F6] hover:text-[#60A5FA]">
          {part}
        </Link>
      );
    }
    // External URL
    if (/^https?:\/\/\S+$/.test(part)) {
      return (
        <a key={i} href={part} target="_blank" rel="noopener noreferrer" className="underline text-[#3B82F6] hover:text-[#60A5FA]">
          {part}
        </a>
      );
    }
    return <span key={i}>{part}</span>;
  });
}

export default function OraclePage() {
  const { currentSite } = useSite();
  const { session, token } = useAuth();
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState('');
  const [loading, setLoading] = useState(false);
  const [streamingContent, setStreamingContent] = useState('');
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, streamingContent, scrollToBottom]);

  useEffect(() => {
    inputRef.current?.focus();
  }, []);

  const handleSubmit = useCallback(async (question: string) => {
    if (!currentSite || !question.trim() || loading) return;

    const userMsg: ChatMessage = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: question.trim(),
      timestamp: Date.now(),
    };

    setMessages(prev => [...prev, userMsg]);
    setInput('');
    setLoading(true);
    setStreamingContent('');

    const accessToken = session?.access_token ?? token;

    try {
      const res = await fetch(
        apiUrl(`/sites/${currentSite.id}/intelligence/oracle`),
        {
          method: 'POST',
          headers: {
            'Content-Type': 'application/json',
            ...(accessToken ? { Authorization: `Bearer ${accessToken}` } : {}),
          },
          body: JSON.stringify({ question }),
        }
      );

      if (!res.ok) {
        throw new Error(`API error ${res.status}`);
      }

      // Try streaming first
      if (res.body) {
        const reader = res.body.getReader();
        const decoder = new TextDecoder();
        let fullText = '';

        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          const chunk = decoder.decode(value, { stream: true });
          fullText += chunk;
          setStreamingContent(fullText);
        }

        // If the response was JSON (non-streaming), parse it
        let finalContent = fullText;
        try {
          const parsed = JSON.parse(fullText);
          // If it's an OracleVerdict-style response, extract meaningful text
          if (parsed.reasoning) {
            const parts: string[] = [];
            if (parsed.reasoning) parts.push(parsed.reasoning);
            if (parsed.recommendation) parts.push(`\n\nRecommendation: ${parsed.recommendation}`);
            if (parsed.similar_posts?.length) {
              parts.push('\n\nRelated posts:');
              parsed.similar_posts.forEach((p: { title: string; url: string }) => {
                parts.push(`- [${p.title}](${p.url})`);
              });
            }
            finalContent = parts.join('\n');
          } else if (parsed.answer) {
            finalContent = parsed.answer;
          } else if (typeof parsed === 'string') {
            finalContent = parsed;
          }
        } catch {
          // Not JSON, use the raw streamed text
        }

        const oracleMsg: ChatMessage = {
          id: `oracle-${Date.now()}`,
          role: 'oracle',
          content: finalContent,
          timestamp: Date.now(),
        };
        setMessages(prev => [...prev, oracleMsg]);
      } else {
        // Fallback: non-streaming
        const data = await res.json();
        const content = data.reasoning || data.answer || JSON.stringify(data);
        const oracleMsg: ChatMessage = {
          id: `oracle-${Date.now()}`,
          role: 'oracle',
          content,
          timestamp: Date.now(),
        };
        setMessages(prev => [...prev, oracleMsg]);
      }
    } catch (err) {
      const errorMsg: ChatMessage = {
        id: `oracle-error-${Date.now()}`,
        role: 'oracle',
        content: `Sorry, I encountered an error: ${err instanceof Error ? err.message : 'Unknown error'}. Please try again.`,
        timestamp: Date.now(),
      };
      setMessages(prev => [...prev, errorMsg]);
    } finally {
      setLoading(false);
      setStreamingContent('');
    }
  }, [currentSite, loading, session?.access_token, token]);

  const handleKeyDown = (e: React.KeyboardEvent<HTMLInputElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      void handleSubmit(input);
    }
  };

  const isEmpty = messages.length === 0 && !loading;

  return (
    <div className="flex flex-col h-[calc(100vh-8rem)] max-w-4xl mx-auto">
      {/* Header */}
      <div className="flex items-center gap-3 mb-4 flex-shrink-0">
        <Link
          href="/today"
          className="p-2 rounded-lg text-[#64748b] hover:text-[#e2e8f0] hover:bg-[#1e293b] transition-colors"
        >
          <ArrowLeft size={18} />
        </Link>
        <div className="flex items-center gap-2.5">
          <Sparkles size={20} className="text-[#3B82F6]" />
          <div>
            <h1 className="text-lg font-semibold text-[#e2e8f0]">Oracle</h1>
            <p className="text-xs text-[#64748b]">Ask anything about your content ecosystem</p>
          </div>
        </div>
      </div>

      {/* Messages area */}
      <div className="flex-1 overflow-y-auto space-y-4 pb-4 pr-2">
        {isEmpty && (
          <div className="flex flex-col items-center justify-center h-full gap-6">
            <div className="flex items-center gap-2">
              <Sparkles size={32} className="text-[#3B82F6]" />
            </div>
            <div className="text-center">
              <h2 className="text-lg font-semibold text-[#e2e8f0] mb-1">What can I help you with?</h2>
              <p className="text-sm text-[#64748b]">Ask me about your content strategy, performance, or any SEO question</p>
            </div>
            <div className="flex flex-wrap gap-2 justify-center max-w-lg">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  onClick={() => void handleSubmit(s)}
                  className="text-sm px-4 py-2 rounded-full bg-[#1e293b] text-[#94a3b8]
                             hover:bg-[#3B82F6]/10 hover:text-[#3B82F6] transition-colors
                             border border-[#334155] hover:border-[#3B82F6]/30"
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div
              className={
                msg.role === 'user'
                  ? 'bg-[#3B82F6] text-white rounded-2xl rounded-tr-sm px-4 py-2 max-w-[70%]'
                  : 'bg-[#13151B] border border-[#23262F] rounded-2xl rounded-tl-sm px-4 py-2 max-w-[70%] text-[#e2e8f0]'
              }
            >
              <div className="text-sm leading-relaxed whitespace-pre-wrap">
                {msg.role === 'oracle' ? renderMessageContent(msg.content) : msg.content}
              </div>
            </div>
          </div>
        ))}

        {/* Streaming response */}
        {loading && streamingContent && (
          <div className="flex justify-start">
            <div className="bg-[#13151B] border border-[#23262F] rounded-2xl rounded-tl-sm px-4 py-2 max-w-[70%] text-[#e2e8f0]">
              <div className="text-sm leading-relaxed whitespace-pre-wrap">
                {renderMessageContent(streamingContent)}
              </div>
            </div>
          </div>
        )}

        {/* Thinking indicator */}
        {loading && !streamingContent && (
          <div className="flex justify-start">
            <div className="bg-[#13151B] border border-[#23262F] rounded-2xl rounded-tl-sm px-4 py-3 text-[#e2e8f0]">
              <div className="flex items-center gap-2">
                <div className="flex gap-1">
                  {[0, 1, 2].map(i => (
                    <div
                      key={i}
                      className="w-2 h-2 rounded-full bg-[#3B82F6] animate-bounce"
                      style={{ animationDelay: `${i * 0.15}s`, animationDuration: '0.6s' }}
                    />
                  ))}
                </div>
                <span className="text-sm text-[#64748b]">Thinking...</span>
              </div>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Input area - fixed at bottom */}
      <div className="flex-shrink-0 border-t border-[#1e293b] pt-4">
        <div className="flex gap-3 items-center">
          <input
            ref={inputRef}
            type="text"
            value={input}
            onChange={e => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask Oracle anything..."
            className="flex-1 rounded-xl bg-[#0a0f1a] border border-[#1e293b] text-sm
                       text-[#e2e8f0] placeholder-[#334155] px-4 py-3 focus:outline-none
                       focus:border-[#3B82F6] transition-colors"
            disabled={loading}
          />
          <button
            onClick={() => void handleSubmit(input)}
            disabled={!input.trim() || loading}
            className="flex-shrink-0 p-3 rounded-xl bg-[#3B82F6] text-white
                       hover:bg-[#2563eb] transition-colors disabled:opacity-40 disabled:cursor-not-allowed"
          >
            <Send size={16} />
          </button>
        </div>
        <p className="text-[10px] text-[#334155] mt-2 text-center">Press Enter to send</p>
      </div>
    </div>
  );
}
