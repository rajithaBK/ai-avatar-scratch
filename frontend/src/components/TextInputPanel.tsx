export interface TextInputPanelProps {
  text: string;
  onTextChange: (next: string) => void;
  onGenerate: () => void;
  onClear: () => void;
  isGenerating: boolean;
  disabled?: boolean;
  errorMessage?: string | null;
}

const SAMPLES = [
  "Hello! Welcome to the demo. I am your AI assistant on a Webex Desk device.",
  "Today's agenda: a short product update, a quick demo, and a Q and A.",
  "Thanks for joining. Please let me know how I can help you today.",
];

export function TextInputPanel(props: TextInputPanelProps) {
  const { text, onTextChange, onGenerate, onClear, isGenerating, disabled, errorMessage } = props;

  return (
    <section className="card" aria-label="Text input">
      <h1>AI Avatar Demo</h1>
      <p className="subtitle">
        Type a message and generate a professional avatar video. Speech is synthesized locally with
        Kokoro TTS, then lip-synced onto your avatar with MuseTalk.
      </p>

      <div className="textarea-wrap">
        <textarea
          className="textarea"
          aria-label="Message to speak"
          placeholder="Type or paste the message you want the avatar to say..."
          value={text}
          maxLength={2000}
          onChange={(e) => onTextChange(e.target.value)}
          disabled={isGenerating || disabled}
          rows={8}
          spellCheck
        />
      </div>

      <div className="actions">
        <button
          type="button"
          className="btn btn-primary"
          onClick={onGenerate}
          disabled={isGenerating || disabled || text.trim().length === 0}
          data-testid="generate-button"
        >
          {isGenerating ? "Generating..." : "Generate Avatar Video"}
        </button>
        <button
          type="button"
          className="btn btn-ghost"
          onClick={onClear}
          disabled={isGenerating || (text.length === 0)}
        >
          Clear
        </button>
      </div>

      <div className="actions" aria-label="Sample prompts">
        {SAMPLES.map((s, i) => (
          <button
            key={i}
            type="button"
            className="btn btn-ghost"
            style={{ minWidth: 0, fontSize: 14, padding: "10px 16px", minHeight: 40 }}
            onClick={() => onTextChange(s)}
            disabled={isGenerating || disabled}
          >
            Sample {i + 1}
          </button>
        ))}
      </div>

      {errorMessage && (
        <p className="error" role="alert" data-testid="error-message">
          {errorMessage}
        </p>
      )}
    </section>
  );
}

export default TextInputPanel;
