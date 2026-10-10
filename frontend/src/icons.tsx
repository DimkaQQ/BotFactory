import type { Icon } from "@phosphor-icons/react";
import {
  AddressBook,
  Alarm,
  Armchair,
  BookOpenText,
  CalendarCheck,
  ChartBarHorizontal,
  ChatCircleText,
  CreditCard,
  FilmSlate,
  Gift,
  GraduationCap,
  HandHeart,
  Image as ImageIcon,
  Megaphone,
  Package,
  PlusCircle,
  Question,
  Robot,
  Storefront,
  Ticket,
  Timer,
  ArrowsClockwise,
  TextAlignLeft,
  Handshake,
  Hand,
  CursorClick,
  UsersThree,
  Sparkle,
} from "@phosphor-icons/react";

import type { BlockType } from "./api/builderApi";

/** Иконки типов блоков: вместо эмодзи, чтобы набор был единым и не зависел от платформы. */
const BLOCK_ICONS: Record<BlockType, Icon> = {
  welcome: Hand,
  description: TextAlignLeft,
  image: ImageIcon,
  video: FilmSlate,
  buttons: CursorClick,
  poll: ChartBarHorizontal,
  delivery: Gift,
  payment: CreditCard,
  contact: AddressBook,
  booking: CalendarCheck,
  delay: Timer,
};

export function BlockIcon({ type, size = 18 }: { type: BlockType; size?: number }) {
  const Glyph = BLOCK_ICONS[type] ?? Sparkle;
  return <Glyph size={size} weight="regular" />;
}

/** Иконки шаблонов по id. Эмодзи в самих шаблонах остаются: это тексты сообщений бота для покупателя. */
const TEMPLATE_ICONS: Record<string, Icon> = {
  "one-time-product": Package,
  subscription: ArrowsClockwise,
  "one-on-one": Handshake,
  "promo-broadcast": Megaphone,
  "quick-menu": CursorClick,
  "salon-booking": Armchair,
  "booking-free": CalendarCheck,
  "shop-showcase": Storefront,
  "faq-support": Question,
  "lead-magnet": Gift,
  "course-lessons": GraduationCap,
  "event-tickets": Ticket,
  donations: HandHeart,
  "feedback-quiz": ChatCircleText,
  blank: PlusCircle,
};

export function TemplateIcon({ id, size = 22 }: { id: string; size?: number }) {
  const Glyph = TEMPLATE_ICONS[id] ?? BookOpenText;
  return <Glyph size={size} weight="regular" />;
}

/** Знак бренда: тёмно-зелёная плитка с роботом. */
export function BrandMark({ size = 32 }: { size?: number }) {
  return (
    <span className="brand-mark" style={{ width: size, height: size }} aria-hidden="true">
      <Robot size={Math.round(size * 0.62)} weight="fill" />
    </span>
  );
}

export { Alarm, UsersThree };
