export type User = { id: string; name: string; email: string };
export type Document = {
  id: string;
  title: string;
  fileName: string;
  kind: string;
  status: string;
  bytes: number;
  pages: number;
  chunks: number;
  createdAt: string;
  error?: string;
};
export type Citation = {
  id: string;
  documentId: string;
  fileName: string;
  page: number;
  text: string;
  score: number;
};
export type Trace = { stage: string; detail: string; at: string };
export type Run = {
  id: string;
  conversationId: string;
  messageId: string;
  status: string;
  mode: string;
  question: string;
  answer: string;
  citations: Citation[];
  trace: Trace[];
  error?: string;
  latencyMs: number;
  createdAt: string;
  updatedAt: string;
};
export type Conversation = {
  id: string;
  title: string;
  createdAt: string;
  updatedAt: string;
};
export type Message = {
  id: string;
  role: string;
  content: string;
  status: string;
  citations: Citation[];
  trace: Trace[];
  createdAt: string;
};
export type Evaluation = {
  id: string;
  name: string;
  questions: number;
  pageHitRate: number | null;
  sourceHitRate: number | null;
  answerCorrectness: number | null;
  contextRecall: number | null;
  faithfulness: number | null;
  latencyMs: number | null;
  source: string;
  retrievalFile: string;
  generationFile: string;
};
export type EvalRow = {
  id: number;
  question: string;
  answer: string;
  reference: string;
  sources: string[];
  pages: number[];
  metrics: Record<string, number>;
  retrieval: Record<string, unknown>;
};
export type EvalDetail = {
  id: string;
  name: string;
  rows: EvalRow[];
  sourceFiles: string[];
};
export type Overview = {
  documents: Document[];
  conversations: Conversation[];
  runCount: number;
  recentRuns: Run[];
  agent: {
    status: string;
    modelConfigured: boolean;
    modelStatus?: string;
    publicDocuments?: number;
  };
  evaluations: Evaluation[];
};

export type Page = "overview" | "documents" | "chat" | "evaluations" | "runs";
