import type { BlockType } from "../api/builderApi";

interface Props {
  type: BlockType;
}

/** A tiny looping mockup of what a block looks like once it's in the chat —
 * shown next to the block library item the pointer is hovering over, so
 * picking a block type isn't a guessing game from an icon and a label. */
export function BlockPreviewFlyout({ type }: Props) {
  if (type === "delay") {
    return (
      <div className="block-preview block-preview--delay" key={type}>
        <div className="block-preview__dots block-preview__dots--solo">
          <span />
          <span />
          <span />
        </div>
        <p className="block-preview__caption">⏱ Пауза — следующий блок придёт чуть позже</p>
      </div>
    );
  }

  return (
    <div className="block-preview" key={type}>
      <div className="block-preview__dots">
        <span />
        <span />
        <span />
      </div>
      <div className="block-preview__row">
        <span className="block-preview__avatar" aria-hidden="true">
          🤖
        </span>
        <div className={`block-preview__bubble block-preview__bubble--${type}`}>{renderInner(type)}</div>
      </div>
    </div>
  );
}

function renderInner(type: BlockType) {
  switch (type) {
    case "welcome":
      return <p className="block-preview__text">👋 Привет! Рады видеть тебя здесь</p>;
    case "description":
      return (
        <div className="block-preview__lines">
          <span className="block-preview__line" style={{ width: "88%" }} />
          <span className="block-preview__line" style={{ width: "64%" }} />
        </div>
      );
    case "image":
      return (
        <div className="block-preview__media">
          <span aria-hidden="true">🖼️</span>
        </div>
      );
    case "video":
      return (
        <div className="block-preview__media block-preview__media--video">
          <span aria-hidden="true">▶</span>
        </div>
      );
    case "buttons":
      return (
        <>
          <p className="block-preview__text">Готов? 🚀</p>
          <span className="block-preview__pill">Купить</span>
        </>
      );
    case "poll":
      return (
        <div className="block-preview__poll">
          <p className="block-preview__text">Что интереснее?</p>
          <span className="block-preview__bar" style={{ "--fill": "76%" } as React.CSSProperties} />
          <span className="block-preview__bar" style={{ "--fill": "40%" } as React.CSSProperties} />
        </div>
      );
    case "delivery":
      return <p className="block-preview__text">🎁 Вот твой материал!</p>;
    default:
      return null;
  }
}
