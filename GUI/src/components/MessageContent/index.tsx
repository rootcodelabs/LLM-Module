import { FC } from 'react';
import './MessageContent.scss';

interface MessageContentProps {
  content: string;
}

const MessageContent: FC<MessageContentProps> = ({ content }) => {
  // Function to parse and render message content with proper formatting
  const renderContent = () => {
    // Split by **References:** pattern
    const referencesMatch = content.match(/\*\*References:\*\*([\s\S]*)/);
    
    if (!referencesMatch) {
      // No references, return plain content with line breaks
      return (
        <div className="message-text">
          {content.split('\n').map((line, index) => (
            <span key={index}>
              {line}
              {index < content.split('\n').length - 1 && <br />}
            </span>
          ))}
        </div>
      );
    }

    // Split content into main text and references
    const mainText = content.substring(0, referencesMatch.index);
    const referencesText = referencesMatch[1].trim();

    // Parse numbered references with URLs
    const referenceLines = referencesText
      .split('\n')
      .filter(line => line.trim())
      .map(line => {
        // Match pattern: "1. https://url" or "1. url"
        const match = line.match(/^(\d+)\.\s+(https?:\/\/[^\s]+)/);
        if (match) {
          return {
            number: match[1],
            url: match[2],
          };
        }
        return null;
      })
      .filter(Boolean);

    return (
      <div className="message-content-wrapper">
        {/* Main text */}
        {mainText && (
          <div className="message-text">
            {mainText.split('\n').map((line, index) => (
              <span key={index}>
                {line}
                {index < mainText.split('\n').length - 1 && <br />}
              </span>
            ))}
          </div>
        )}

        {/* References section */}
        {referenceLines.length > 0 && (
          <div className="message-references">
            <strong className="references-title">References:</strong>
            <ol className="references-list">
              {referenceLines.map((ref, index) => (
                <li key={index}>
                  <a
                    href={ref!.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    className="reference-link"
                  >
                    {ref!.url}
                  </a>
                </li>
              ))}
            </ol>
          </div>
        )}
      </div>
    );
  };

  return <>{renderContent()}</>;
};

export default MessageContent;
