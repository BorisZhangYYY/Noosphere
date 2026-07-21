import { useTheme } from "../theme";

export function Atmosphere() {
  const { resolvedTheme } = useTheme();
  return (
    <div className="atmosphere" aria-hidden="true">
      {resolvedTheme === "light" ? (
        <>
          <div className="sun" />
          <div className="cloud cloud-one"><span /><span /><span /></div>
          <div className="cloud cloud-two"><span /><span /><span /></div>
          <div className="cloud cloud-three"><span /><span /><span /></div>
          <div className="cloud cloud-four"><span /><span /><span /></div>
          <div className="wind-lines"><i /><i /><i /></div>
          <div className="wind-particles">{Array.from({ length: 12 }, (_, index) => <i key={index} style={{ "--particle-index": index } as React.CSSProperties} />)}</div>
          <div className="birds"><i /><i /><i /><i /><i /></div>
        </>
      ) : (
        <>
          <div className="moon"><span /></div>
          <div className="stars">
            {Array.from({ length: 56 }, (_, index) => (
              <i
                key={index}
                style={{
                  "--star-index": index,
                  "--star-left": `${(index * 37 + 8) % 94}%`,
                  "--star-top": `${(index * 17 + 6) % 58}%`
                } as React.CSSProperties}
              />
            ))}
          </div>
          <div className="shooting-stars"><i /><i /><i /></div>
        </>
      )}
    </div>
  );
}
