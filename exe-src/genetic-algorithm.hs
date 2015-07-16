import Control.Lens
import Control.Monad

import qualified Data.Map as M
import qualified Data.Text as T
import qualified Data.Text.IO as T
import SpaceWeather.CmdArgs
import SpaceWeather.Format
import SpaceWeather.Prediction
import SpaceWeather.Regressor.General
import SpaceWeather.FeaturePack
import System.System
import System.IO.Unsafe

type Genome = M.Map (String, FilePath) Bool

genome :: Lens' PredictionStrategyGS Genome
genome = featureSchemaPackUsed . fspFilenamePairs . l
  where
    l :: Lens' [(String, FilePath)] Genome
    l = lens g s
    g :: [(String, FilePath)] -> Genome
    g xs = M.fromList $ zip xs $ repeat True

    s :: [(String, FilePath)] -> Genome -> [(String, FilePath)]
    s _ xs = map fst $ filter snd $ M.toList xs

-- mutate :: PredictionStrategyGS -> IO PredictionStrategyGS


featureFiles :: [String]
featureFiles = unsafePerformIO $ do
  files <- readSystem0 "ls wavelet-features/*.txt"
  return $ map ("file://./" ++ ) $ words files


main :: IO ()
main = withWorkDir $ do
  Right cclass <- fmap decode $ T.readFile "resource/best-strategies-3/CClass.yml"
  Right mclass <- fmap decode $ T.readFile "resource/best-strategies-3/MClass.yml"
  Right xclass <- fmap decode $ T.readFile "resource/best-strategies-3/XClass.yml"

  mapM_ T.putStrLn $ map encode [cclass, mclass, xclass :: PredictionStrategyGS]
