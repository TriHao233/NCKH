export default function QuestionContent({ text }) {
  const parts = String(text || '').split(/(```[^\n`]*\n[\s\S]*?```)/g);
  return (
    <div className="draft-item-text">
      {parts.map((part, index) => {
        const block = part.match(/^```([^\n`]*)\n([\s\S]*?)```$/);
        return block
          ? <pre className="draft-question-code" key={index}><code>{block[2].trim()}</code></pre>
          : <span key={index}>{part}</span>;
      })}
    </div>
  );
}
