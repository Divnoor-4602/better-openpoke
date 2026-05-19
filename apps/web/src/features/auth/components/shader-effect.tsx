import {
  Dither,
  FilmGrain,
  GridDistortion,
  ImageTexture,
  Shader,
} from 'shaders/react'

export const ShaderEffect = () => {
  return (
    <Shader className="absolute inset-0 w-full h-full">
      <ImageTexture
        objectFit="cover"
        url="https://data.shaders.com/storage/v1/object/public/user-uploaded-images/user_3DuobzafRfHSxH4Lf9P6PMgzHqW/1vmssEciMwJz.jpeg"
      />
      <ImageTexture
        objectFit="contain"
        transform={{
          anchorY: 0.7,

          scale: 0.1,
        }}
        url="https://data.shaders.com/storage/v1/object/public/user-uploaded-images/user_3DuobzafRfHSxH4Lf9P6PMgzHqW/UhRKY7PywUu3.png"
      />

      <GridDistortion decay={3.1} gridSize={25} intensity={1.5} radius={2} />
      <Dither
        colorA="#ffffff"
        colorB="transparent"
        colorMode="source"
        pattern="bayer8"
        pixelSize={2}
        threshold={0.79}
        transform={{ scale: 1 }}
        visible
      />
      <FilmGrain visible={false} />
    </Shader>
  )
}
