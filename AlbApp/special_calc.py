import math

class SCalc:
    @staticmethod
    def linear_interpolation(x, x0 ,x1, y1,y0):
        return y0 + (x - x0) * (y1 - y0) / (x1 - x0)

    @staticmethod
    def square_root_of_the_sum_of_squares(fb, ob):
        return math.hypot(fb, ob)

    @staticmethod
    def scale_force(F, S_child, S_adult):
        return F * (S_child / S_adult)

    @staticmethod
    def Fc(t, F_cmax):
        """F_c(t) = F_cmax · 10⁻³ · poly(t), схема Горнера"""
        poly = t * (3.62495690883228
             + t * (1.64651497111425e-1
             + t * (-1.67101914899229e-3
             + t * (5.98882225167948e-6
             + t * (-9.20373741104191e-9
             + t *   5.12306842296552e-12)))))
        return F_cmax * 1e-3 * poly
    


